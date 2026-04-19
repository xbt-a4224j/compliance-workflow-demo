from __future__ import annotations

import json
from textwrap import dedent

import pytest

from compliance_workflow_demo.dsl import compile_rule, load_rule
from compliance_workflow_demo.executor import (
    CheckResult,
    ExecutorError,
    LlmAnswer,
    build_prompt,
    execute_check,
)
from compliance_workflow_demo.executor.check import _parse_llm_json, _resolve_page
from compliance_workflow_demo.ingest import DocChunk, Document
from compliance_workflow_demo.router import (
    CompletionRequest,
    CompletionResponse,
    MockAdapter,
    RetryPolicy,
    Router,
)

# --- helpers ----------------------------------------------------------------

def _doc() -> Document:
    return Document(
        id="docsha",
        chunks=(
            DocChunk(text="The fund delivered strong returns last year.", page=1),
            DocChunk(text="Past performance is no guarantee of future results.", page=2),
            DocChunk(text="Fees are disclosed in the prospectus.", page=3),
        ),
    )


def _leaf(yaml_text: str):
    rule = load_rule(dedent(yaml_text))
    graph = compile_rule(rule)
    return graph.nodes[graph.roots[rule.id]]


def _router_emitting(text: str) -> Router:
    def responder(_req: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            text=text, input_tokens=1, output_tokens=1, model="m", provider="mock"
        )

    return Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )


# --- prompt template dispatch ----------------------------------------------

def test_build_prompt_dispatches_by_op():
    requires = _leaf(
        """
        id: R1
        name: r
        op: REQUIRES_CLAUSE
        clause: past performance is disclosed
        """
    )
    forbids = _leaf(
        """
        id: R2
        name: f
        op: FORBIDS_PHRASE
        phrase: guaranteed returns
        """
    )
    cites = _leaf(
        """
        id: R3
        name: c
        op: CITES
        target: SEC risk disclaimer
        """
    )

    s_req, u_req = build_prompt(requires, "doc")
    s_for, u_for = build_prompt(forbids, "doc")
    s_cit, u_cit = build_prompt(cites, "doc")

    assert "past performance is disclosed" in u_req
    assert "guaranteed returns" in u_for
    assert "SEC risk disclaimer" in u_cit
    assert s_req != s_for != s_cit  # each op has its own system prompt
    # JSON contract present in every user prompt
    for u in (u_req, u_for, u_cit):
        assert "JSON" in u
        assert "passed" in u


def test_build_prompt_rejects_aggregator():
    rule = load_rule(
        dedent(
            """
            id: R1
            name: agg
            op: ALL_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: a
            """
        )
    )
    graph = compile_rule(rule)
    root = graph.nodes[graph.roots["R1"]]
    with pytest.raises(ValueError, match="not a leaf"):
        build_prompt(root, "doc")


# --- JSON parsing ----------------------------------------------------------

def test_parse_plain_json():
    answer = _parse_llm_json('{"passed": true, "evidence": "quote", "confidence": 0.9}')
    assert isinstance(answer, LlmAnswer)
    assert answer.passed is True
    assert answer.evidence == "quote"


def test_parse_strips_markdown_fences():
    text = '```json\n{"passed": false, "evidence": null, "confidence": 0.4}\n```'
    answer = _parse_llm_json(text)
    assert answer.passed is False
    assert answer.evidence is None


def test_parse_extracts_object_from_chatter():
    text = 'Sure! Here is the JSON: {"passed": true, "evidence": "x", "confidence": 0.8}. Done.'
    answer = _parse_llm_json(text)
    assert answer.passed is True


def test_parse_rejects_no_json():
    with pytest.raises(ExecutorError, match="no JSON"):
        _parse_llm_json("the answer is yes")


def test_parse_rejects_schema_violation():
    with pytest.raises(ExecutorError, match="schema"):
        _parse_llm_json('{"passed": true, "confidence": 1.5}')  # confidence out of range


def test_parse_rejects_extra_field():
    with pytest.raises(ExecutorError):
        _parse_llm_json(
            '{"passed": true, "evidence": "x", "confidence": 0.5, "page": 7}'
        )


# --- page_ref resolution ----------------------------------------------------

def test_page_ref_resolves_to_chunk_containing_evidence():
    doc = _doc()
    page = _resolve_page("Past performance is no guarantee of future results.", doc)
    assert page == 2


def test_page_ref_handles_whitespace_normalization():
    doc = _doc()
    # extra whitespace in the LLM's quote shouldn't defeat the match
    page = _resolve_page("Past   performance is no\nguarantee of future results.", doc)
    assert page == 2


def test_page_ref_none_when_evidence_not_in_doc():
    doc = _doc()
    assert _resolve_page("totally fabricated quote that isn't there", doc) is None


def test_page_ref_none_when_evidence_none():
    assert _resolve_page(None, _doc()) is None


# --- execute_check end-to-end ----------------------------------------------

@pytest.mark.asyncio
async def test_execute_check_happy_path():
    leaf = _leaf(
        """
        id: R1
        name: r
        op: REQUIRES_CLAUSE
        clause: past performance is disclosed
        """
    )
    payload = json.dumps(
        {
            "passed": True,
            "evidence": "Past performance is no guarantee of future results.",
            "confidence": 0.92,
        }
    )
    router = _router_emitting(payload)

    result = await execute_check(leaf, _doc(), router)

    assert isinstance(result, CheckResult)
    assert result.check_id == leaf.id           # stitched from node, not LLM
    assert result.passed is True
    assert result.confidence == 0.92
    assert result.page_ref == 2                 # from chunker, not LLM


@pytest.mark.asyncio
async def test_execute_check_passes_check_id_through_unchanged():
    leaf = _leaf(
        """
        id: R1
        name: r
        op: CITES
        target: SEC
        """
    )
    payload = json.dumps({"passed": False, "evidence": None, "confidence": 0.1})
    result = await execute_check(leaf, _doc(), _router_emitting(payload))
    assert result.check_id == leaf.id
    assert result.page_ref is None
    assert result.evidence is None


@pytest.mark.asyncio
async def test_execute_check_page_ref_none_when_llm_hallucinates_quote():
    leaf = _leaf(
        """
        id: R1
        name: r
        op: REQUIRES_CLAUSE
        clause: anything
        """
    )
    payload = json.dumps(
        {"passed": True, "evidence": "this quote is not in the doc", "confidence": 0.7}
    )
    result = await execute_check(leaf, _doc(), _router_emitting(payload))
    assert result.passed is True
    assert result.evidence == "this quote is not in the doc"
    assert result.page_ref is None  # hallucinated quote → no page


@pytest.mark.asyncio
async def test_execute_check_aggregator_rejected():
    rule = load_rule(
        dedent(
            """
            id: R1
            name: agg
            op: ALL_OF
            children:
              - op: REQUIRES_CLAUSE
                clause: a
            """
        )
    )
    graph = compile_rule(rule)
    root = graph.nodes[graph.roots["R1"]]
    router = _router_emitting('{"passed": true, "evidence": null, "confidence": 1.0}')
    with pytest.raises(ValueError, match="leaf"):
        await execute_check(root, _doc(), router)


@pytest.mark.asyncio
async def test_execute_check_propagates_executor_error_on_bad_json():
    leaf = _leaf(
        """
        id: R1
        name: r
        op: CITES
        target: SEC
        """
    )
    router = _router_emitting("totally not json")
    with pytest.raises(ExecutorError):
        await execute_check(leaf, _doc(), router)
