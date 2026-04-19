from __future__ import annotations

from typing import Literal

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
    # Override which adapter is tried first so callers can force a run through
    # a specific provider. Enables side-by-side provider comparison in Jaeger.
    primary: Literal["anthropic", "openai"] | None = None
    # Bypass the findings cache for this run — every leaf re-calls the LLM.
    # Useful for demos: makes the next run actually expensive + slow so the
    # cache hit on the run after that is visible by contrast.
    skip_cache: bool = False


class CreateRunResponse(BaseModel):
    """The DAG ships with the run_id so the UI can render every node as
    'pending' immediately, without waiting on the SSE stream — see #19."""

    run_id: str
    dag: ExecutionGraph
    # trace_id lets the client paste this run's trace directly into Jaeger
    # (or its Compare view against another run). No in-app A/B plumbing —
    # the comparison is entirely a Jaeger UI affair.
    trace_id: str | None = None


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


class RuleDetail(BaseModel):
    """A single rule with its authored YAML + compiled DAG. Surfaces the
    human-authored policy next to the DAG of atomic LLM checks it compiled
    into, so the two can be read side-by-side in the Rules view."""
    id: str
    name: str
    op: str
    yaml_source: str
    dag: ExecutionGraph


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


class DbOverview(BaseModel):
    """Most-recent rows from each persistence table — powers the UI Admin tab
    as a lightweight alternative to opening psql / DataGrip."""
    connected: bool
    runs: list[dict]
    findings: list[dict]
    router_calls: list[dict]


class LogsResponse(BaseModel):
    """In-memory log buffer snapshot for the UI Logs tab. Newest entry first."""
    capacity: int
    entries: list  # list[LogEntry] — kept loose to avoid a circular import
