from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict

from compliance_workflow_demo.executor.result import CheckResult


class RunStatus(StrEnum):
    PASSED = "passed"      # every rule passed cleanly
    FAILED = "failed"      # at least one rule failed cleanly (LLM said no)
    DEGRADED = "degraded"  # at least one rule couldn't be evaluated (a leaf errored)


class NodeFinding(BaseModel):
    """One row of the run's verdict table — one per node in the DAG.

    `errored=True` means we couldn't evaluate this node (a leaf raised, or an
    aggregator's children include errors that we couldn't compensate for).
    `passed` defaults to False on errored nodes — compliance defaults to "no"
    on uncertainty.
    """

    model_config = ConfigDict(frozen=True)

    node_id: str
    op: str
    passed: bool
    errored: bool = False
    check_result: CheckResult | None = None      # leaves only
    children_passed: tuple[bool, ...] | None = None  # aggregators only


class RunResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str                          # UUID — per-run, no content to hash
    status: RunStatus
    per_rule: dict[str, bool]            # rule_id → final passed (best-effort)
    per_rule_errored: dict[str, bool]    # rule_id → could-not-evaluate
    findings: dict[str, NodeFinding]     # node_id → finding (every node in DAG)
    errors: dict[str, str]               # node_id → error message (errored leaves only)


# --- streaming events for #17 SSE -------------------------------------------

EventKind = Literal["run_started", "check_started", "check_finished", "run_finished"]


class OrchestratorEvent(BaseModel):
    """Lightweight event the orchestrator emits at lifecycle points.

    Single shape with a `kind` tag rather than a pydantic discriminated union.
    There's only one consumer (the SSE generator in #17) and it'll switch on
    `kind`; the discriminated-union ceremony isn't worth it here.
    """

    model_config = ConfigDict(frozen=True)

    kind: EventKind
    run_id: str
    node_id: str | None = None
    finding: NodeFinding | None = None
    result: RunResult | None = None
