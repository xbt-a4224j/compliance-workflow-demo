from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from compliance_workflow_demo.dsl.graph import ExecutionGraph
from compliance_workflow_demo.executor.run import OrchestratorEvent, RunResult


@dataclass
class RunState:
    """Per-run in-memory bookkeeping.

    The orchestrator's on_event callback puts events on `events`. The SSE
    handler awaits items off the queue and writes them as text frames. When
    `result` is set (after run_finished), the SSE handler closes the stream.
    """

    run_id: str
    rule_id: str
    doc_id: str
    dag: ExecutionGraph
    events: asyncio.Queue[OrchestratorEvent] = field(default_factory=asyncio.Queue)
    completed: asyncio.Event = field(default_factory=asyncio.Event)
    result: RunResult | None = None
    task: asyncio.Task[RunResult] | None = None


class RunRegistry:
    """In-memory store of all runs the API knows about. Survives the process
    lifetime; not durable. Long-finished runs are kept around so the UI can
    GET them after refresh; eviction would be added if the registry ever
    grew large enough to matter."""

    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}

    def add(self, run: RunState) -> None:
        self._runs[run.run_id] = run

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def all(self) -> list[RunState]:
        return list(self._runs.values())
