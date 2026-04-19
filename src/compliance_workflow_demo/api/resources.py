from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from compliance_workflow_demo.api.schemas import (
    DbOverview,
    DocPage,
    DocSummary,
    DocText,
    LogsResponse,
    RuleDetail,
    RuleSummary,
)
from compliance_workflow_demo.db.connection import connect
from compliance_workflow_demo.dsl import compile_rules

router = APIRouter()


@router.get("/rules", response_model=list[RuleSummary])
async def list_rules(request: Request) -> list[RuleSummary]:
    rules = request.app.state.rules
    return [
        RuleSummary(id=rule.id, name=rule.name, op=rule.root.op)
        for rule in rules.values()
    ]


@router.get("/rules/{rule_id}", response_model=RuleDetail)
async def get_rule(rule_id: str, request: Request) -> RuleDetail:
    """Rule authored-YAML + its compiled atomic-check DAG. Feeds the Rules
    view, which renders YAML ↔ DAG side-by-side."""
    rules = request.app.state.rules
    sources = request.app.state.rule_sources
    rule = rules.get(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"unknown rule_id: {rule_id!r}")
    graph = compile_rules([rule])
    return RuleDetail(
        id=rule.id,
        name=rule.name,
        op=rule.root.op,
        yaml_source=sources[rule_id],
        dag=graph,
    )


@router.get("/docs", response_model=list[DocSummary])
async def list_docs(request: Request) -> list[DocSummary]:
    docs = request.app.state.docs
    return [
        DocSummary(
            id=name,
            title=_extract_title(name, doc),
            sha256=doc.id,
            pages=len({c.page for c in doc.chunks}),
        )
        for name, doc in docs.items()
    ]


@router.get("/docs/{doc_id}/text", response_model=DocText)
async def get_doc_text(doc_id: str, request: Request) -> DocText:
    """Return per-page text so the UI can render the doc and highlight
    evidence quotes returned by the LLM."""
    docs = request.app.state.docs
    doc = docs.get(doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"unknown doc_id: {doc_id!r}")
    # Concatenate chunks belonging to the same page so split chunks render
    # as one continuous page block in the UI.
    by_page: dict[int, list[str]] = {}
    for chunk in doc.chunks:
        by_page.setdefault(chunk.page, []).append(chunk.text)
    pages = [DocPage(page=p, text="\n\n".join(by_page[p])) for p in sorted(by_page)]
    return DocText(
        id=doc_id,
        title=_extract_title(doc_id, doc),
        sha256=doc.id,
        pages=pages,
    )


@router.get("/admin/db/overview", response_model=DbOverview)
async def db_overview(request: Request) -> DbOverview:
    """Recent rows from runs / findings / router_calls for the Admin UI tab.
    Read-only. Limited to 20 rows per table to keep the payload small."""
    db_url = request.app.state.db_url
    if db_url is None:
        return DbOverview(connected=False, runs=[], findings=[], router_calls=[])

    async def _rows(conn, sql: str) -> list[dict]:
        async with conn.cursor() as cur:
            await cur.execute(sql)
            cols = [c.name for c in cur.description]
            return [
                {c: (v.isoformat() if hasattr(v, "isoformat") else v) for c, v in zip(cols, row)}
                for row in await cur.fetchall()
            ]

    conn = await connect(db_url)
    try:
        runs = await _rows(
            conn,
            "SELECT r.id, r.rule_id, r.doc_id, r.status, "
            "       r.started_at, r.finished_at, "
            "       ROUND(COALESCE(SUM(rc.cost_usd), 0)::numeric, 6)::float "
            "         AS cost_usd "
            "FROM runs r LEFT JOIN router_calls rc ON rc.run_id = r.id "
            "GROUP BY r.id "
            "ORDER BY r.started_at DESC LIMIT 20",
        )
        findings = await _rows(
            conn,
            "SELECT run_id, check_id, doc_id, passed, evidence, page_ref, confidence, created_at "
            "FROM findings ORDER BY created_at DESC LIMIT 20",
        )
        router_calls = await _rows(
            conn,
            "SELECT run_id, check_id, provider, tokens_in, tokens_out, cost_usd, latency_ms "
            "FROM router_calls ORDER BY run_id DESC LIMIT 20",
        )
    finally:
        await conn.close()

    return DbOverview(
        connected=True, runs=runs, findings=findings, router_calls=router_calls
    )


@router.get("/admin/logs", response_model=LogsResponse)
async def get_logs(
    request: Request, min_level: str = "INFO", limit: int = 200
) -> LogsResponse:
    """Snapshot of the in-memory log buffer. Newest first. `min_level` filters
    to WARNING+ / ERROR / etc; `limit` caps the response size."""
    buf = request.app.state.log_buffer
    entries = buf.snapshot(min_level=min_level, limit=limit)
    return LogsResponse(capacity=buf._buf.maxlen or 0, entries=entries)


def _extract_title(stem: str, doc) -> str:
    """First non-empty line of the first chunk — for our corpus that's the
    fund name (e.g. 'Northwind Capital Growth Fund'). Falls back to the
    filename stem if the doc looks empty."""
    if not doc.chunks:
        return stem
    for line in doc.chunks[0].text.splitlines():
        line = line.strip()
        if line:
            # Title-case the line if it's all caps (synth docs use uppercase
            # headers); leave mixed-case alone (real prospectus already cased).
            return line.title() if line.isupper() else line
    return stem
