from __future__ import annotations

import os
from collections.abc import AsyncIterator

# create_app() evaluates at import-time (module-level `app = create_app()` in
# api/app.py) and refuses to start without AUTH_TOKEN. Set a dummy value here
# before any test module imports it. The autouse _env_setup fixture in
# test_api.py refreshes this to the same value for each test.
os.environ.setdefault("AUTH_TOKEN", "test-token-xyz")

import psycopg
import pytest
import pytest_asyncio

from compliance_workflow_demo.db.connection import database_url
from compliance_workflow_demo.db.migrate import apply_migrations


def _db_reachable(url: str) -> bool:
    try:
        conn = psycopg.connect(url, connect_timeout=2)
    except Exception:
        return False
    conn.close()
    return True


@pytest.fixture(scope="session")
def database_url_or_skip() -> str:
    """Skip the DB-backed tests in CI / on machines without a running Postgres.
    Local development hits the docker-compose Postgres at the default URL."""
    url = database_url()
    if not _db_reachable(url):
        pytest.skip(f"Postgres not reachable at {url}")
    return url


@pytest_asyncio.fixture(scope="session")
async def _migrated(database_url_or_skip: str) -> None:
    """Apply migrations once per test session on a separate connection so
    schema changes are committed and visible to all subsequent test
    transactions."""
    conn = await psycopg.AsyncConnection.connect(database_url_or_skip, autocommit=True)
    try:
        await apply_migrations(conn)
    finally:
        await conn.close()


@pytest_asyncio.fixture
async def db_conn(
    database_url_or_skip: str, _migrated: None
) -> AsyncIterator[psycopg.AsyncConnection]:
    """One connection per test wrapped in a transaction that rolls back at
    teardown so tests can't leak data into each other."""
    conn = await psycopg.AsyncConnection.connect(database_url_or_skip, autocommit=False)
    try:
        async with conn.transaction(force_rollback=True):
            yield conn
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def _otel_endpoint_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    # Avoid a real OTLP exporter trying to phone home during unrelated tests.
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://127.0.0.1:1")  # nowhere
    if "OTEL_SDK_DISABLED" not in os.environ:
        monkeypatch.setenv("OTEL_SDK_DISABLED", "true")
