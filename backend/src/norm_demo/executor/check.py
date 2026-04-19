from __future__ import annotations

import json
import re

from pydantic import ValidationError

from compliance_workflow_demo.dsl.graph import GraphNode
from compliance_workflow_demo.executor.prompts import build_prompt
from compliance_workflow_demo.executor.result import CheckResult, LlmAnswer
from compliance_workflow_demo.ingest.types import Document
from compliance_workflow_demo.router.router import Router
from compliance_workflow_demo.router.types import CompletionRequest


class ExecutorError(Exception):
    """Raised when the LLM response can't be parsed as a valid LlmAnswer."""


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.MULTILINE)
_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def _parse_llm_json(text: str) -> LlmAnswer:
    """Tolerant JSON extraction: strips ``` fences, falls back to first {...} match."""
    cleaned = _FENCE_RE.sub("", text).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        match = _OBJECT_RE.search(cleaned)
        if match is None:
            raise ExecutorError(f"no JSON object in LLM response: {text[:200]!r}") from None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            raise ExecutorError(f"malformed JSON from LLM: {text[:200]!r}") from e

    try:
        return LlmAnswer.model_validate(data)
    except ValidationError as e:
        raise ExecutorError(f"LLM JSON failed schema: {e}") from e


def _resolve_page(evidence: str | None, doc: Document) -> int | None:
    """Match the LLM's evidence quote back to a chunk to recover the page.

    LLMs hallucinate page numbers when asked directly. The chunker stamps real
    page numbers onto every chunk; we trust those. If the evidence isn't found
    in any chunk (LLM paraphrased or made it up), page_ref is None — better
    than a confidently wrong number.
    """
    if not evidence:
        return None
    needle = " ".join(evidence.split())  # collapse whitespace
    for chunk in doc.chunks:
        haystack = " ".join(chunk.text.split())
        if needle in haystack:
            return chunk.page
    return None


async def execute_check(node: GraphNode, doc: Document, router: Router) -> CheckResult:
    """Run one atomic LLM check against a document.

    Stitches together: node-derived check_id, LLM-derived passed/evidence/
    confidence, chunker-derived page_ref. The LLM is only trusted for the
    semantic verdict — never for ids or page numbers.
    """
    if not node.is_leaf:
        raise ValueError(f"execute_check requires a leaf node, got op={node.op}")

    system, user = build_prompt(node, doc.joined_text())
    response = await router.route(CompletionRequest(system=system, user=user))
    answer = _parse_llm_json(response.text)

    page_ref = _resolve_page(answer.evidence, doc)
    passed = answer.passed
    evidence = answer.evidence

    # Hallucination guard: for FORBIDS_PHRASE, a passed=false verdict says
    # "the forbidden phrase IS present in the doc" — and the LLM is supposed
    # to quote it. If the quote can't be grounded back to any chunk, the LLM
    # fabricated the quote (we've seen this when the doc contains the word
    # in a disclaiming context, e.g. "not guaranteed by the FDIC"). Treat
    # ungroundable violation claims as non-findings rather than trusting
    # the LLM's hallucination.
    if node.op == "FORBIDS_PHRASE" and passed is False and page_ref is None:
        passed = True
        evidence = None  # the hallucinated quote isn't worth surfacing

    return CheckResult(
        check_id=node.id,
        passed=passed,
        evidence=evidence,
        page_ref=page_ref,
        confidence=answer.confidence,
    )
