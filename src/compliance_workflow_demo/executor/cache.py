"""The cache contract the orchestrator depends on.

Lives here (executor side, no db imports) so the orchestrator stays
decoupled from persistence. Implementations (Postgres, Redis, an
in-memory LRU for tests) satisfy the Protocol from wherever they want.
"""

from __future__ import annotations

from typing import Protocol

from compliance_workflow_demo.executor.result import CheckResult


class FindingsCache(Protocol):
    """Read-only cache the orchestrator consults before each leaf execution.

    Hit → skip the LLM call entirely. Miss → run execute_check normally.
    Writes happen at end-of-run via repo.persist_run, not through this
    Protocol — the orchestrator stays free of write side effects.
    """

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None: ...


class NoCache:
    """Default: every leaf call is a cache miss. Lets the orchestrator's
    cache hook stay always-on without the test suite needing a database."""

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None:
        return None
