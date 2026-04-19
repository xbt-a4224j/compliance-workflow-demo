from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Protocol

from compliance_workflow_demo.dsl.graph import ExecutionGraph, GraphNode
from compliance_workflow_demo.executor.check import ExecutorError, execute_check
from compliance_workflow_demo.executor.result import CheckResult
from compliance_workflow_demo.executor.run import (
    NodeFinding,
    OrchestratorEvent,
    RunResult,
    RunStatus,
)
from compliance_workflow_demo.ingest.types import Document
from compliance_workflow_demo.router.router import Router
from compliance_workflow_demo.router.types import ProviderUnavailable

EventHandler = Callable[[OrchestratorEvent], Awaitable[None]]


class _Cache(Protocol):
    async def get(self, check_id: str, doc_id: str) -> CheckResult | None: ...


class _NoCache:
    async def get(self, check_id: str, doc_id: str) -> CheckResult | None:
        return None


@dataclass
class Orchestrator:
    """Walks an ExecutionGraph against a Document.

    v1: in-process fan-out via asyncio.gather. v2 (out of demo scope) is the
    same execute_check behind a Redis queue + worker pool, swapped at the
    seam where _fan_out_leaves currently lives.

    The optional `cache` is consulted before each leaf execution. A hit
    short-circuits the LLM call entirely — this is the live payoff of
    content-addressed (check_id, doc_id) keys (#6 + #14). Cache writes are
    not the orchestrator's job; persisting the run via db.repo.persist_run
    populates the cache for future calls.
    """

    router: Router
    on_event: EventHandler | None = None
    cache: _Cache = field(default_factory=_NoCache)

    async def run(
        self,
        graph: ExecutionGraph,
        doc: Document,
        *,
        run_id: str | None = None,
    ) -> RunResult:
        # Caller can pre-generate the run_id so the value returned by an API
        # endpoint matches the run_id stamped on every emitted event. Default
        # to a fresh UUID for direct-use callers (tests, scripts).
        run_id = run_id or str(uuid.uuid4())
        await self._emit(OrchestratorEvent(kind="run_started", run_id=run_id))

        findings: dict[str, NodeFinding] = {}
        errors: dict[str, str] = {}

        # 1. Fan out every leaf in parallel. Iterating graph.nodes (the deduped
        # dict) — not graph.topo_order with filtering — guarantees a shared
        # leaf runs exactly once even if it appears under multiple aggregators.
        leaves = [n for n in graph.nodes.values() if n.is_leaf]
        leaf_outcomes = await asyncio.gather(
            *(self._run_leaf(node, doc, run_id) for node in leaves)
        )
        for node, outcome in zip(leaves, leaf_outcomes, strict=True):
            findings[node.id] = outcome.finding
            if outcome.error_message is not None:
                errors[node.id] = outcome.error_message

        # 2. Walk topo_order; aggregators come after their children by construction.
        for nid in graph.topo_order:
            node = graph.nodes[nid]
            if node.is_leaf:
                continue
            child_findings = [findings[c] for c in node.child_ids]
            passed, errored = _aggregate(node.op, child_findings)
            finding = NodeFinding(
                node_id=nid,
                op=node.op,
                passed=passed,
                errored=errored,
                children_passed=tuple(c.passed for c in child_findings),
            )
            findings[nid] = finding
            await self._emit(
                OrchestratorEvent(
                    kind="check_finished", run_id=run_id, node_id=nid, finding=finding
                )
            )

        # 3. Roll up to per-rule + run status.
        per_rule = {rid: findings[root].passed for rid, root in graph.roots.items()}
        per_rule_errored = {
            rid: findings[root].errored for rid, root in graph.roots.items()
        }
        status = _run_status(per_rule, per_rule_errored)

        result = RunResult(
            run_id=run_id,
            status=status,
            per_rule=per_rule,
            per_rule_errored=per_rule_errored,
            findings=findings,
            errors=errors,
        )
        await self._emit(
            OrchestratorEvent(kind="run_finished", run_id=run_id, result=result)
        )
        return result

    async def _run_leaf(
        self, node: GraphNode, doc: Document, run_id: str
    ) -> _LeafOutcome:
        await self._emit(
            OrchestratorEvent(kind="check_started", run_id=run_id, node_id=node.id)
        )

        cached = await self.cache.get(node.id, doc.id)
        if cached is not None:
            finding = NodeFinding(
                node_id=node.id,
                op=node.op,
                passed=cached.passed,
                check_result=cached,
            )
            await self._emit(
                OrchestratorEvent(
                    kind="check_finished",
                    run_id=run_id,
                    node_id=node.id,
                    finding=finding,
                )
            )
            return _LeafOutcome(finding=finding, error_message=None)

        try:
            check = await execute_check(node, doc, self.router)
        except (ProviderUnavailable, ExecutorError) as e:
            finding = NodeFinding(
                node_id=node.id, op=node.op, passed=False, errored=True
            )
            await self._emit(
                OrchestratorEvent(
                    kind="check_finished",
                    run_id=run_id,
                    node_id=node.id,
                    finding=finding,
                )
            )
            return _LeafOutcome(finding=finding, error_message=f"{type(e).__name__}: {e}")
        # PermanentError is intentionally not caught — bad config aborts the run.

        finding = NodeFinding(
            node_id=node.id,
            op=node.op,
            passed=check.passed,
            check_result=check,
        )
        await self._emit(
            OrchestratorEvent(
                kind="check_finished", run_id=run_id, node_id=node.id, finding=finding
            )
        )
        return _LeafOutcome(finding=finding, error_message=None)

    async def _emit(self, event: OrchestratorEvent) -> None:
        if self.on_event is not None:
            await self.on_event(event)


@dataclass(frozen=True)
class _LeafOutcome:
    finding: NodeFinding
    error_message: str | None


def _aggregate(op: str, children: list[NodeFinding]) -> tuple[bool, bool]:
    """Return (passed, errored) for an aggregator over its children.

    Truth table (the ANY_OF asymmetry is the load-bearing part):

        ALL_OF: all clean passes              → (True, False)
        ALL_OF: any clean fail                → (False, False)  -- definitive
        ALL_OF: any errored, no clean fail    → (False, True)   -- degraded
        ANY_OF: any clean pass                → (True, False)   -- a clean pass
                                                                   makes errors moot
        ANY_OF: no clean pass, any errored    → (False, True)   -- degraded
        ANY_OF: all clean failures            → (False, False)
    """
    if op == "ALL_OF":
        if any(not c.passed and not c.errored for c in children):
            return False, False  # already definitively failed by a clean child
        if any(c.errored for c in children):
            return False, True
        return True, False

    if op == "ANY_OF":
        if any(c.passed and not c.errored for c in children):
            return True, False
        if any(c.errored for c in children):
            return False, True
        return False, False

    raise ValueError(f"unknown aggregator op: {op!r}")


def _run_status(
    per_rule: dict[str, bool], per_rule_errored: dict[str, bool]
) -> RunStatus:
    if any(per_rule_errored.values()):
        return RunStatus.DEGRADED
    if all(per_rule.values()):
        return RunStatus.PASSED
    return RunStatus.FAILED
