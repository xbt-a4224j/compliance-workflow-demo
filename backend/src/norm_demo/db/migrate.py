from __future__ import annotations

from pathlib import Path

import psycopg

_MIGRATIONS_TABLE = """
CREATE TABLE IF NOT EXISTS _migrations (
    name        TEXT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""


def migrations_dir() -> Path:
    """Path to the numbered SQL migration files. Computed from this module's
    location so it works regardless of where the process was launched from."""
    return Path(__file__).resolve().parent.parent.parent.parent / "migrations"


async def apply_migrations(
    conn: psycopg.AsyncConnection, *, directory: Path | None = None
) -> list[str]:
    """Apply every *.sql in `directory` whose name isn't yet in _migrations.

    Order is filename-sorted (the 001_, 002_, ... prefix is the contract).
    Each migration runs in its own transaction so a partial failure leaves
    the prior migrations applied and recoverable.

    Returns the names of migrations applied this call (empty if all current).
    """
    directory = directory or migrations_dir()
    if not directory.is_dir():
        raise FileNotFoundError(f"migrations directory not found: {directory}")

    # Bookkeeping table + read of applied set must work regardless of whether
    # the caller has wrapped us in a transaction. Inner transaction blocks
    # below become savepoints in that case, which is exactly what we want.
    async with conn.transaction(), conn.cursor() as cur:
        await cur.execute(_MIGRATIONS_TABLE)
        await cur.execute("SELECT name FROM _migrations")
        applied = {row[0] for row in await cur.fetchall()}

    files = sorted(p for p in directory.glob("*.sql"))
    newly_applied: list[str] = []

    for path in files:
        if path.name in applied:
            continue
        sql = path.read_text()
        async with conn.transaction(), conn.cursor() as cur:
            await cur.execute(sql)
            await cur.execute(
                "INSERT INTO _migrations (name) VALUES (%s)", (path.name,)
            )
        newly_applied.append(path.name)

    return newly_applied
