from __future__ import annotations

import json
from textwrap import dedent

import pytest

from compliance_workflow_demo.dsl import compile_rule, load_rule
from compliance_workflow_demo.executor import Orchestrator, RunStatus
from compliance_workflow_demo.executor.result import CheckResult
from compliance_workflow_demo.ingest import DocChunk, Document
from compliance_workflow_demo.router import (
    CompletionResponse,
    MockAdapter,
    RetryPolicy,
    Router,
)


class InMemoryCache:
    """Simulates a populated FindingsCache without touching Postgres."""

    def __init__(self) -> None:
        self.store: dict[tuple[str, str], CheckResult] = {}
        self.lookups: list[tuple[str, str]] = []

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None:
        self.lookups.append((check_id, doc_id))
        return self.store.get((check_id, doc_id))


def _doc() -> Document:
    return Document(
        id="docsha",
        chunks=(DocChunk(text="anything", page=1),),
    )


@pytest.mark.asyncio
async def test_cache_hit_skips_llm_call_entirely():
    rule = load_rule(
        dedent(
            """
            id: R1
            name: r
            op: REQUIRES_CLAUSE
            clause: anything
            """
        )
    )
    graph = compile_rule(rule)
    leaf_id = graph.roots["R1"]

    adapter = MockAdapter(
        responder=lambda _r: CompletionResponse(
            text=json.dumps({"passed": True, "evidence": "x", "confidence": 1.0}),
            input_tokens=1, output_tokens=1, model="m", provider="mock",
        )
    )
    router = Router(
        adapters=[adapter],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )

    cache = InMemoryCache()
    cache.store[(leaf_id, "docsha")] = CheckResult(
        check_id=leaf_id, passed=False, evidence="cached quote",
        page_ref=7, confidence=0.42,
    )

    result = await Orchestrator(router=router, cache=cache).run(graph, _doc())

    # The LLM was never called — cached result short-circuited.
    assert adapter.calls == []
    assert cache.lookups == [(leaf_id, "docsha")]
    # The cached values flow through to the run result.
    assert result.status is RunStatus.FAILED
    finding = result.findings[leaf_id]
    assert finding.check_result is not None
    assert finding.check_result.evidence == "cached quote"
    assert finding.check_result.page_ref == 7


@pytest.mark.asyncio
async def test_cache_miss_falls_through_to_llm():
    rule = load_rule(
        dedent(
            """
            id: R1
            name: r
            op: REQUIRES_CLAUSE
            clause: anything
            """
        )
    )
    graph = compile_rule(rule)

    adapter = MockAdapter(
        responder=lambda _r: CompletionResponse(
            text=json.dumps({"passed": True, "evidence": "fresh", "confidence": 0.8}),
            input_tokens=1, output_tokens=1, model="m", provider="mock",
        )
    )
    router = Router(
        adapters=[adapter],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )

    cache = InMemoryCache()  # empty store
    result = await Orchestrator(router=router, cache=cache).run(graph, _doc())

    assert len(adapter.calls) == 1  # cache miss → LLM ran
    assert len(cache.lookups) == 1
    assert result.status is RunStatus.PASSED
