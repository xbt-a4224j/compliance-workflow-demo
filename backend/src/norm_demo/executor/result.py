from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LlmAnswer(BaseModel):
    """The structured JSON we ask the LLM to emit for every atomic check.

    Deliberately small: just the call's verdict, a quote, and a confidence.
    `check_id` and `page_ref` are stitched on by the executor (#12), not the
    LLM — LLMs hallucinate page numbers and id strings.
    """

    model_config = ConfigDict(extra="forbid")

    passed: bool
    evidence: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)


class CheckResult(BaseModel):
    """The executor's per-leaf output. Aggregated up the DAG by the orchestrator."""

    model_config = ConfigDict(frozen=True)

    check_id: str
    passed: bool
    evidence: str | None
    page_ref: int | None
    confidence: float
