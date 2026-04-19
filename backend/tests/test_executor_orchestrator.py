from __future__ import annotations

import json
from textwrap import dedent

import pytest

from compliance_workflow_demo.dsl import compile_rule, compile_rules, load_rule
from compliance_workflow_demo.executor import (
    Orchestrator,
    OrchestratorEvent,
    RunStatus,
)
from compliance_workflow_demo.ingest import DocChunk, Document
from compliance_workflow_demo.router import (
    CompletionRequest,
    CompletionResponse,
    MockAdapter,
    PermanentError,
    RetryPolicy,
    Router,
    TransientError,
)

# --- helpers ----------------------------------------------------------------

def _doc() -> Document:
    return Document(
        id="docsha",
        chunks=(
            DocChunk(text="Past performance is no guarantee of future results.", page=1),
            DocChunk(text="The fund charges a 1% management fee.", page=2),
        ),
    )


def _rule(yaml_text: str):
    return load_rule(dedent(yaml_text))


def _ok(evidence: str = "Past performance is no guarantee of future results.") -> str:
    return json.dumps({"passed": True, "evidence": evidence, "confidence": 0.9})


def _fail() -> str:
    return json.dumps({"passed": False, "evidence": None, "confidence": 0.8})


def _router_with(responder) -> Router:
    return Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )


def _verdict_router(verdicts: dict[str, str]) -> tuple[Router, MockAdapter]:
    """Router whose response depends on a substring match in the user prompt.

    Lets a single test express "this clause should pass, that phrase should
    fail" without writing a new responder per test.
    """
    adapter = MockAdapter()

    def responder(req: CompletionRequest) -> CompletionResponse:
        for needle, payload in verdicts.items():
            if needle in req.user:
                return CompletionResponse(
                    text=payload, input_tokens=1, output_tokens=1, model="m", provider="mock"
                )
        raise AssertionError(f"no verdict configured for prompt: {req.user[:120]!r}")

    adapter.responder = responder
    return (
        Router(
            adapters=[adapter],
            retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
        ),
        adapter,
    )


# --- happy paths -----------------------------------------------------------

@pytest.mark.asyncio
async def test_single_leaf_passing_rule():
    rule = _rule(
        """
        id: R1
        name: r
        op: REQUIRES_CLAUSE
        clause: past performance is disclosed
        """
    )
    graph = compile_rule(rule)
    orch = Orchestrator(router=_router_with(lambda _r: CompletionResponse(
        text=_ok(), input_tokens=1, output_tokens=1, model="m", provider="mock"
    )))

    result = await orch.run(graph, _doc())

    assert result.status is RunStatus.PASSED
    assert result.per_rule == {"R1": True}
    assert result.errors == {}
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_all_of_passes_when_all_children_pass():
    rule = _rule(
        """
        id: R1
        name: all
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: past performance
          - op: REQUIRES_CLAUSE
            clause: management fee
        """
    )
    graph = compile_rule(rule)
    router, _ = _verdict_router({"past performance": _ok(), "management fee": _ok()})
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.PASSED
    assert result.per_rule == {"R1": True}
    # 2 leaves + 1 aggregator = 3 findings
    assert len(result.findings) == 3


@pytest.mark.asyncio
async def test_all_of_fails_when_any_child_fails():
    rule = _rule(
        """
        id: R1
        name: all
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: past performance
          - op: REQUIRES_CLAUSE
            clause: management fee
        """
    )
    graph = compile_rule(rule)
    router, _ = _verdict_router({"past performance": _ok(), "management fee": _fail()})
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.FAILED
    assert result.per_rule == {"R1": False}
    assert result.per_rule_errored == {"R1": False}  # cleanly failed, not degraded


@pytest.mark.asyncio
async def test_any_of_passes_if_one_child_passes():
    rule = _rule(
        """
        id: R1
        name: any
        op: ANY_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: past performance
          - op: REQUIRES_CLAUSE
            clause: nonexistent
        """
    )
    graph = compile_rule(rule)
    router, _ = _verdict_router({"past performance": _ok(), "nonexistent": _fail()})
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.PASSED
    assert result.per_rule == {"R1": True}


# --- the truth-table edges -------------------------------------------------

@pytest.mark.asyncio
async def test_all_of_with_one_clean_fail_and_one_error_is_failed_not_degraded():
    """ALL_OF: a clean fail is definitive — error on a sibling doesn't matter."""
    rule = _rule(
        """
        id: R1
        name: all
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: clean_fail_marker
          - op: REQUIRES_CLAUSE
            clause: errors_out_marker
        """
    )
    graph = compile_rule(rule)

    def responder(req):
        if "clean_fail_marker" in req.user:
            return CompletionResponse(
                text=_fail(), input_tokens=1, output_tokens=1, model="m", provider="mock"
            )
        raise TransientError("provider down")  # makes this leaf "errored"

    router = Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.FAILED  # not DEGRADED — the clean fail is definitive
    assert result.per_rule_errored == {"R1": False}
    assert len(result.errors) == 1  # one leaf errored, but its rule still cleanly failed


@pytest.mark.asyncio
async def test_any_of_with_one_clean_pass_and_one_error_is_passed():
    """ANY_OF: a clean pass makes a sibling error moot — rule satisfied."""
    rule = _rule(
        """
        id: R1
        name: any
        op: ANY_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: clean_pass_marker
          - op: REQUIRES_CLAUSE
            clause: errors_out_marker
        """
    )
    graph = compile_rule(rule)

    def responder(req):
        if "clean_pass_marker" in req.user:
            return CompletionResponse(
                text=_ok(), input_tokens=1, output_tokens=1, model="m", provider="mock"
            )
        raise TransientError("provider down")

    router = Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.PASSED
    assert result.per_rule_errored == {"R1": False}


@pytest.mark.asyncio
async def test_any_of_with_one_clean_fail_and_one_error_is_degraded():
    """ANY_OF: no clean pass + an error → we don't know if the errored leg
    would have saved us, so we report degraded."""
    rule = _rule(
        """
        id: R1
        name: any
        op: ANY_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: clean_fail_marker
          - op: REQUIRES_CLAUSE
            clause: errors_out_marker
        """
    )
    graph = compile_rule(rule)

    def responder(req):
        if "clean_fail_marker" in req.user:
            return CompletionResponse(
                text=_fail(), input_tokens=1, output_tokens=1, model="m", provider="mock"
            )
        raise TransientError("provider down")

    router = Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.DEGRADED
    assert result.per_rule_errored == {"R1": True}


# --- the content-addressing payoff -----------------------------------------

@pytest.mark.asyncio
async def test_shared_leaf_executes_only_once():
    """Two rules that share a leaf → the shared leaf runs ONCE, not twice.

    This is the live payoff of content-addressed node ids from #6.
    """
    rules = [
        _rule(
            """
            id: R1
            name: a
            op: ALL_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: shared_marker
              - op: REQUIRES_CLAUSE
                clause: r1_only
            """
        ),
        _rule(
            """
            id: R2
            name: b
            op: ANY_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: shared_marker
              - op: REQUIRES_CLAUSE
                clause: r2_only
            """
        ),
    ]
    graph = compile_rules(rules)

    router, adapter = _verdict_router({
        "shared_marker": _ok(),
        "r1_only": _ok(),
        "r2_only": _ok(),
    })
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.PASSED
    # 3 distinct leaves: shared, r1_only, r2_only. NOT 4.
    assert len(adapter.calls) == 3
    shared_calls = [c for c in adapter.calls if "shared_marker" in c.user]
    assert len(shared_calls) == 1


# --- error handling --------------------------------------------------------

@pytest.mark.asyncio
async def test_permanent_error_aborts_the_run():
    """PermanentError = bad config / bad request. The orchestrator does NOT
    swallow it into 'degraded' — it propagates so the operator sees it."""
    rule = _rule(
        """
        id: R1
        name: r
        op: REQUIRES_CLAUSE
        clause: anything
        """
    )
    graph = compile_rule(rule)
    router = Router(
        adapters=[MockAdapter(raises=PermanentError("missing api key"))],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )

    with pytest.raises(PermanentError):
        await Orchestrator(router=router).run(graph, _doc())


@pytest.mark.asyncio
async def test_executor_error_records_to_degraded():
    """LLM returned malformed JSON → ExecutorError → leaf marked degraded,
    error recorded, run continues for the rest of the graph."""
    rules = [
        _rule(
            """
            id: BAD
            name: malformed
            op: REQUIRES_CLAUSE
            clause: triggers_bad_json
            """
        ),
        _rule(
            """
            id: GOOD
            name: ok
            op: REQUIRES_CLAUSE
            clause: triggers_ok
            """
        ),
    ]
    graph = compile_rules(rules)

    def responder(req):
        if "triggers_bad_json" in req.user:
            return CompletionResponse(
                text="not even close to JSON",
                input_tokens=1, output_tokens=1, model="m", provider="mock",
            )
        return CompletionResponse(
            text=_ok(), input_tokens=1, output_tokens=1, model="m", provider="mock"
        )

    router = Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )
    result = await Orchestrator(router=router).run(graph, _doc())

    assert result.status is RunStatus.DEGRADED
    assert result.per_rule == {"BAD": False, "GOOD": True}
    assert result.per_rule_errored == {"BAD": True, "GOOD": False}
    assert len(result.errors) == 1


# --- streaming events ------------------------------------------------------

@pytest.mark.asyncio
async def test_emits_lifecycle_events_in_order():
    rule = _rule(
        """
        id: R1
        name: r
        op: ALL_OF
        children:
          - op: REQUIRES_CLAUSE
            clause: a
          - op: REQUIRES_CLAUSE
            clause: b
        """
    )
    graph = compile_rule(rule)
    router, _ = _verdict_router({"a": _ok(), "b": _ok()})

    events: list[OrchestratorEvent] = []

    async def collect(e: OrchestratorEvent) -> None:
        events.append(e)

    await Orchestrator(router=router, on_event=collect).run(graph, _doc())

    kinds = [e.kind for e in events]
    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    # 2 leaves: each gets check_started + check_finished. Then aggregator
    # gets one check_finished. Then run_finished.
    assert kinds.count("check_started") == 2
    assert kinds.count("check_finished") == 3  # 2 leaves + 1 aggregator
    # The terminal event carries the full result for SSE consumers.
    assert events[-1].result is not None
    assert events[-1].result.status is RunStatus.PASSED


@pytest.mark.asyncio
async def test_no_event_handler_is_fine():
    """on_event=None should be a no-op, not a crash."""
    rule = _rule(
        """
        id: R1
        name: r
        op: REQUIRES_CLAUSE
        clause: anything
        """
    )
    graph = compile_rule(rule)
    router = _router_with(lambda _r: CompletionResponse(
        text=_ok(), input_tokens=1, output_tokens=1, model="m", provider="mock"
    ))
    result = await Orchestrator(router=router).run(graph, _doc())  # no on_event
    assert result.status is RunStatus.PASSED
