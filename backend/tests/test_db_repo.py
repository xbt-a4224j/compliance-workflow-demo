from __future__ import annotations

import uuid

import psycopg
import pytest

from compliance_workflow_demo.db.repo import (
    get_cached_finding,
    insert_findings,
    insert_router_call,
    insert_run,
    persist_run,
    update_run_status,
)
from compliance_workflow_demo.executor.result import CheckResult
from compliance_workflow_demo.executor.run import NodeFinding, RunResult, RunStatus


def _check(check_id: str, *, passed: bool = True) -> CheckResult:
    return CheckResult(
        check_id=check_id,
        passed=passed,
        evidence="quote here",
        page_ref=2,
        confidence=0.9,
    )


def _leaf_finding(check_id: str, *, passed: bool = True) -> NodeFinding:
    return NodeFinding(
        node_id=check_id,
        op="REQUIRES_CLAUSE",
        passed=passed,
        check_result=_check(check_id, passed=passed),
    )


def _aggregator_finding(node_id: str) -> NodeFinding:
    return NodeFinding(
        node_id=node_id,
        op="ALL_OF",
        passed=True,
        children_passed=(True, True),
    )


@pytest.mark.asyncio
async def test_insert_run_then_update_status(db_conn: psycopg.AsyncConnection):
    run_id = str(uuid.uuid4())
    await insert_run(db_conn, run_id=run_id, rule_id="R1", doc_id="docsha")
    await update_run_status(db_conn, run_id=run_id, status=RunStatus.FAILED)

    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT status, finished_at FROM runs WHERE id = %s", (run_id,)
        )
        row = await cur.fetchone()

    assert row is not None
    assert row[0] == "failed"
    assert row[1] is not None  # finished_at populated


@pytest.mark.asyncio
async def test_insert_findings_skips_aggregators(db_conn: psycopg.AsyncConnection):
    run_id = str(uuid.uuid4())
    await insert_run(db_conn, run_id=run_id, rule_id="R1", doc_id="docsha")

    findings = [
        _leaf_finding("leaf1"),
        _leaf_finding("leaf2", passed=False),
        _aggregator_finding("agg1"),  # should be skipped
    ]
    inserted = await insert_findings(
        db_conn, run_id=run_id, doc_id="docsha", findings=findings
    )

    assert inserted == 2
    async with db_conn.cursor() as cur:
        await cur.execute("SELECT count(*) FROM findings WHERE run_id = %s", (run_id,))
        (count,) = await cur.fetchone()
    assert count == 2


@pytest.mark.asyncio
async def test_get_cached_finding_returns_most_recent(
    db_conn: psycopg.AsyncConnection,
):
    """Two runs over the same (check_id, doc_id) — cache returns the latest."""
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())
    await insert_run(db_conn, run_id=run_a, rule_id="R1", doc_id="docsha")
    await insert_run(db_conn, run_id=run_b, rule_id="R1", doc_id="docsha")

    await insert_findings(
        db_conn, run_id=run_a, doc_id="docsha", findings=[_leaf_finding("leaf1", passed=True)]
    )
    await insert_findings(
        db_conn, run_id=run_b, doc_id="docsha", findings=[_leaf_finding("leaf1", passed=False)]
    )

    cached = await get_cached_finding(db_conn, check_id="leaf1", doc_id="docsha")
    assert cached is not None
    assert cached.passed is False  # the more recent run wins
    assert cached.check_id == "leaf1"


@pytest.mark.asyncio
async def test_get_cached_finding_miss_returns_none(db_conn: psycopg.AsyncConnection):
    cached = await get_cached_finding(db_conn, check_id="unknown", doc_id="docsha")
    assert cached is None


@pytest.mark.asyncio
async def test_get_cached_finding_isolated_per_doc(db_conn: psycopg.AsyncConnection):
    """Same check_id against a different doc must not leak as a cache hit."""
    run_id = str(uuid.uuid4())
    await insert_run(db_conn, run_id=run_id, rule_id="R1", doc_id="doc_a")
    await insert_findings(
        db_conn, run_id=run_id, doc_id="doc_a", findings=[_leaf_finding("leaf1")]
    )

    cached_a = await get_cached_finding(db_conn, check_id="leaf1", doc_id="doc_a")
    cached_b = await get_cached_finding(db_conn, check_id="leaf1", doc_id="doc_b")
    assert cached_a is not None
    assert cached_b is None


@pytest.mark.asyncio
async def test_insert_router_call(db_conn: psycopg.AsyncConnection):
    run_id = str(uuid.uuid4())
    await insert_run(db_conn, run_id=run_id, rule_id="R1", doc_id="docsha")
    await insert_router_call(
        db_conn,
        run_id=run_id,
        check_id="leaf1",
        provider="anthropic",
        tokens_in=120,
        tokens_out=40,
        latency_ms=312,
    )

    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT provider, tokens_in, latency_ms FROM router_calls WHERE run_id = %s",
            (run_id,),
        )
        row = await cur.fetchone()

    assert row == ("anthropic", 120, 312)


@pytest.mark.asyncio
async def test_persist_run_writes_run_and_findings_atomically(
    db_conn: psycopg.AsyncConnection,
):
    run_id = str(uuid.uuid4())
    result = RunResult(
        run_id=run_id,
        status=RunStatus.FAILED,
        per_rule={"R1": False},
        per_rule_errored={"R1": False},
        findings={
            "leaf1": _leaf_finding("leaf1", passed=True),
            "leaf2": _leaf_finding("leaf2", passed=False),
            "agg":   _aggregator_finding("agg"),
        },
        errors={},
    )

    await persist_run(db_conn, rule_id="R1", doc_id="docsha", result=result)

    async with db_conn.cursor() as cur:
        await cur.execute("SELECT status FROM runs WHERE id = %s", (run_id,))
        (status,) = await cur.fetchone()
        await cur.execute("SELECT count(*) FROM findings WHERE run_id = %s", (run_id,))
        (count,) = await cur.fetchone()

    assert status == "failed"
    assert count == 2  # two leaves; aggregator skipped
