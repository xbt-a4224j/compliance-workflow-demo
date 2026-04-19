from __future__ import annotations

import psycopg
import pytest

from compliance_workflow_demo.db.migrate import apply_migrations, migrations_dir


@pytest.mark.asyncio
async def test_migrations_dir_resolves_to_real_directory():
    d = migrations_dir()
    assert d.is_dir()
    assert any(p.name.endswith(".sql") for p in d.iterdir())


@pytest.mark.asyncio
async def test_apply_migrations_is_idempotent(db_conn: psycopg.AsyncConnection):
    """Re-applying migrations against a schema that already has them must
    no-op — the _migrations table is the source of truth."""
    second = await apply_migrations(db_conn)
    assert second == []  # already applied by the fixture
