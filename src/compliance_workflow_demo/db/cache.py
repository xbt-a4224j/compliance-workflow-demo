"""Postgres-backed implementation of the executor's FindingsCache contract.

The Protocol itself lives in executor/cache.py so the orchestrator doesn't
have to import from db/. This file is just one concrete satisfier.
"""

from __future__ import annotations

from dataclasses import dataclass

from compliance_workflow_demo.db.connection import connect
from compliance_workflow_demo.db.repo import get_cached_finding
from compliance_workflow_demo.executor.result import CheckResult


@dataclass
class PostgresFindingsCache:
    """Opens a fresh async connection per lookup. Necessary because the
    orchestrator fans leaves out in parallel via asyncio.gather, and psycopg3
    async connections don't support concurrent queries on a single conn.
    At demo scale the connect cost is invisible; for production swap in a
    psycopg_pool.AsyncConnectionPool behind the same get() signature."""
    db_url: str

    async def get(self, check_id: str, doc_id: str) -> CheckResult | None:
        conn = await connect(self.db_url)
        try:
            return await get_cached_finding(conn, check_id=check_id, doc_id=doc_id)
        finally:
            await conn.close()
