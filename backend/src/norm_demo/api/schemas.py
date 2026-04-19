from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from compliance_workflow_demo.dsl.graph import ExecutionGraph
from compliance_workflow_demo.executor.run import RunResult


class CreateRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    doc_id: str = Field(description="The doc stem (e.g. 'synth_fund_01'), not the sha256")
    # Optional rule subset; omit (or empty) to evaluate every loaded rule.
    # Compiling multiple rules together produces a single DAG; the orchestrator
    # then reports per-rule verdicts. Shared sub-expressions across rules
    # collapse to one node via the content-hash id, so a leaf used by N rules
    # only runs once.
    rule_ids: list[str] | None = None


class CreateRunResponse(BaseModel):
    """The DAG ships with the run_id so the UI can render every node as
    'pending' immediately, without waiting on the SSE stream — see #19."""

    run_id: str
    dag: ExecutionGraph


class GetRunResponse(BaseModel):
    run_id: str
    rule_id: str
    doc_id: str
    dag: ExecutionGraph
    result: RunResult | None  # None while still running


class RuleSummary(BaseModel):
    id: str
    name: str
    op: str  # the root op — quick hint for UI list rendering


class DocSummary(BaseModel):
    id: str           # the doc stem (filename without extension)
    title: str        # human-friendly name extracted from the doc's first line
    sha256: str       # content-addressed id
    pages: int


class DocPage(BaseModel):
    page: int
    text: str


class DocText(BaseModel):
    """Per-page text for a document, used by the UI's evidence-highlight pane."""
    id: str
    title: str
    sha256: str
    pages: list[DocPage]
