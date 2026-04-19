from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import psycopg

from compliance_workflow_demo.db.repo import get_cached_finding
from compliance_workflow_demo.executor.result import CheckResult


class FindingsCache(Protocol):
    """Read-only cache the orchestrator consults before each leaf execution.

    Hit → skip the LLM call entirely. Miss → run execute_check normally.
    Writes happen at end-of-run via repo.persist_run, not through this
    protocol — the orchestrator stays free of write side effects.
    """

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None: ...


class NoCache:
    """Default: every leaf call is a cache miss. Lets the orchestrator's
    cache hook stay always-on without the test suite needing a database."""

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None:
        return None


@dataclass
class PostgresFindingsCache:
    conn: psycopg.AsyncConnection

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None:
        return await get_cached_finding(self.conn, check_id=check_id, doc_id=doc_id)
