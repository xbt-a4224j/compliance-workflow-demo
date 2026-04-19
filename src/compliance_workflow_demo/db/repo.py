from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

import psycopg

from compliance_workflow_demo.executor.result import CheckResult
from compliance_workflow_demo.executor.run import NodeFinding, RunResult, RunStatus


async def insert_run(
    conn: psycopg.AsyncConnection,
    *,
    run_id: str,
    rule_id: str,
    doc_id: str,
    status: RunStatus = RunStatus.PASSED,
) -> None:
    """Initial insert at run start. Status is updated at completion via
    update_run_status; passing the wrong default here is intentional — callers
    should always update before commit, and a stale 'passed' is louder than
    a stale 'running' if the orchestrator dies mid-flight."""
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO runs (id, rule_id, doc_id, status, started_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (run_id, rule_id, doc_id, status.value, datetime.now(UTC)),
        )


async def update_run_status(
    conn: psycopg.AsyncConnection,
    *,
    run_id: str,
    status: RunStatus,
    finished_at: datetime | None = None,
) -> None:
    finished = finished_at or datetime.now(UTC)
    async with conn.cursor() as cur:
        await cur.execute(
            "UPDATE runs SET status = %s, finished_at = %s WHERE id = %s",
            (status.value, finished, run_id),
        )


async def insert_findings(
    conn: psycopg.AsyncConnection,
    *,
    run_id: str,
    doc_id: str,
    findings: Iterable[NodeFinding],
) -> int:
    """Bulk-insert leaf findings for a run. Aggregator findings are skipped —
    they're computed deterministically from the leaves and don't need to be
    stored. Returns the number of rows inserted."""
    rows = []
    for f in findings:
        if f.check_result is None:
            continue  # aggregators have no leaf payload to persist
        cr: CheckResult = f.check_result
        rows.append(
            (run_id, f.node_id, doc_id, cr.passed, cr.evidence, cr.page_ref, cr.confidence)
        )
    if not rows:
        return 0

    async with conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO findings "
            "(run_id, check_id, doc_id, passed, evidence, page_ref, confidence) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            rows,
        )
    return len(rows)


async def insert_router_call(
    conn: psycopg.AsyncConnection,
    *,
    run_id: str,
    check_id: str,
    provider: str,
    tokens_in: int,
    tokens_out: int,
    latency_ms: int,
    cost_usd: float | None = None,
) -> None:
    """Per-LLM-call observability. Wired in #11 (deferred); table exists now
    so the orchestrator can be retrofitted without another migration."""
    async with conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO router_calls "
            "(run_id, check_id, provider, tokens_in, tokens_out, cost_usd, latency_ms) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (run_id, check_id, provider, tokens_in, tokens_out, cost_usd, latency_ms),
        )


async def get_cached_finding(
    conn: psycopg.AsyncConnection,
    *,
    check_id: str,
    doc_id: str,
) -> CheckResult | None:
    """The cache lookup that makes content-addressed ids worth doing.

    Picks the most recent finding for (check_id, doc_id) — re-running the
    same rule over the same doc returns this row instead of calling the LLM.
    """
    async with conn.cursor() as cur:
        await cur.execute(
            "SELECT passed, evidence, page_ref, confidence "
            "FROM findings WHERE check_id = %s AND doc_id = %s "
            "ORDER BY created_at DESC LIMIT 1",
            (check_id, doc_id),
        )
        row = await cur.fetchone()

    if row is None:
        return None

    return CheckResult(
        check_id=check_id,
        passed=row[0],
        evidence=row[1],
        page_ref=row[2],
        confidence=row[3],
    )


async def persist_run(
    conn: psycopg.AsyncConnection,
    *,
    rule_id: str,
    doc_id: str,
    result: RunResult,
) -> None:
    """End-of-run write: a single transaction for the run row + all findings."""
    async with conn.transaction():
        await insert_run(
            conn,
            run_id=result.run_id,
            rule_id=rule_id,
            doc_id=doc_id,
            status=result.status,
        )
        await insert_findings(
            conn,
            run_id=result.run_id,
            doc_id=doc_id,
            findings=result.findings.values(),
        )
        await update_run_status(
            conn,
            run_id=result.run_id,
            status=result.status,
        )
