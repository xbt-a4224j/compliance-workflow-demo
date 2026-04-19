from __future__ import annotations

import os

import psycopg

DEFAULT_DATABASE_URL = "postgresql://compliance:compliance@localhost:5432/compliance"


def database_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)


async def connect(url: str | None = None) -> psycopg.AsyncConnection:
    """Open a single async connection. Caller manages the lifecycle.

    No pool yet — the demo's leaf count and concurrency are well under any
    pool's break-even. Add psycopg_pool when the FastAPI route in #17 grows
    real concurrency or when latency profiling shows the connect cost.
    """
    return await psycopg.AsyncConnection.connect(url or database_url())
