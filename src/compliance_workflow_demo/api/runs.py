from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from opentelemetry import trace

from compliance_workflow_demo.api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    GetRunResponse,
)
from compliance_workflow_demo.api.state import RunState
from compliance_workflow_demo.db.cache import NoCache, PostgresFindingsCache
from compliance_workflow_demo.db.connection import connect
from compliance_workflow_demo.db.repo import persist_run
from compliance_workflow_demo.dsl import compile_rules
from compliance_workflow_demo.executor import Orchestrator
from compliance_workflow_demo.executor.run import OrchestratorEvent, RunResult
from compliance_workflow_demo.router.router import Router
from compliance_workflow_demo.router.types import RouterCallRecord

router = APIRouter()
log = logging.getLogger(__name__)


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(req: CreateRunRequest, request: Request) -> CreateRunResponse:
    """Compile the rule, kick off the orchestrator as a background task, and
    return run_id + DAG immediately so the UI can render pending tiles."""
    rules = request.app.state.rules
    docs = request.app.state.docs
    registry = request.app.state.registry
    adapters = request.app.state.adapters

    doc = docs.get(req.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"unknown doc_id: {req.doc_id!r}")

    if req.rule_ids:
        unknown = [rid for rid in req.rule_ids if rid not in rules]
        if unknown:
            raise HTTPException(status_code=404, detail=f"unknown rule_ids: {unknown}")
        selected_rules = [rules[rid] for rid in req.rule_ids]
    else:
        selected_rules = list(rules.values())

    graph = compile_rules(selected_rules)
    run_id = str(uuid.uuid4())
    rule_label = ",".join(r.id for r in selected_rules)
    state = RunState(run_id=run_id, rule_id=rule_label, doc_id=req.doc_id, dag=graph)

    async def on_event(event: OrchestratorEvent) -> None:
        await state.events.put(event)

    db_url = request.app.state.db_url

    # Per-run Router so req.primary reorders the failover chain AND so the
    # on_call hook collects records scoped to THIS run. Always per-run now;
    # the shared app.state.router is effectively a template.
    call_records: list[RouterCallRecord] = []

    async def record_call(rec: RouterCallRecord) -> None:
        call_records.append(rec)

    if req.primary is not None:
        primary_a = next((a for a in adapters if a.provider == req.primary), None)
        if primary_a is None:
            raise HTTPException(
                status_code=400,
                detail=f"primary {req.primary!r} not configured "
                f"(available: {[a.provider for a in adapters]})",
            )
        ordered = [primary_a, *[a for a in adapters if a.provider != req.primary]]
    else:
        ordered = list(adapters)
    llm_router = Router(adapters=ordered, on_call=record_call)

    cache: NoCache | PostgresFindingsCache = (
        PostgresFindingsCache(db_url=db_url)
        if db_url is not None and not req.skip_cache
        else NoCache()
    )
    if req.skip_cache:
        log.info("run %s requested skip_cache — bypassing findings cache", run_id)

    async def runner() -> RunResult:
        try:
            orch = Orchestrator(
                router=llm_router, on_event=on_event, cache=cache
            )
            result = await orch.run(
                graph, doc, run_id=run_id, primary=req.primary
            )
            state.result = result
            log.info(
                "run %s finished status=%s rules=%s doc=%s",
                run_id,
                result.status,
                rule_label,
                req.doc_id,
            )

            # End-of-run write: run + findings + router_calls in one
            # transaction. Use doc.id (sha256) not req.doc_id (stem) so the
            # (check_id, doc_id) cache key stays content-addressed — a doc
            # served under a different filename still hits the same cache.
            # Swallow DB errors so a Postgres blip doesn't poison the run
            # result the UI already streamed via SSE.
            if db_url is not None:
                try:
                    conn = await connect(db_url)
                    try:
                        await persist_run(
                            conn,
                            rule_id=rule_label,
                            doc_id=doc.id,
                            result=result,
                            router_calls=call_records,
                        )
                    finally:
                        await conn.close()
                except Exception as e:  # noqa: BLE001 — best-effort persist
                    log.warning("persist_run failed for %s: %s", run_id, e)
            return result
        except Exception as e:  # noqa: BLE001 — surface in logs even if SSE caught it
            log.error("run %s crashed: %s", run_id, e, exc_info=True)
            raise
        finally:
            state.completed.set()

    state.task = asyncio.create_task(runner())
    registry.add(state)
    log.info(
        "run %s started rules=%s doc=%s primary=%s",
        run_id,
        rule_label,
        req.doc_id,
        req.primary or "default",
    )

    # Trace_id from the active HTTP span lets the client open this run in
    # Jaeger directly, or paste two trace_ids into Jaeger's Compare view.
    span = trace.get_current_span()
    trace_id_hex: str | None = None
    if span is not None:
        ctx = span.get_span_context()
        if ctx.trace_id:
            trace_id_hex = format(ctx.trace_id, "032x")

    return CreateRunResponse(run_id=run_id, dag=graph, trace_id=trace_id_hex)


@router.get("/runs/{run_id}", response_model=GetRunResponse)
async def get_run(run_id: str, request: Request) -> GetRunResponse:
    state = request.app.state.registry.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id!r}")
    return GetRunResponse(
        run_id=state.run_id,
        rule_id=state.rule_id,
        doc_id=state.doc_id,
        dag=state.dag,
        result=state.result,
    )


@router.get("/runs/{run_id}/stream")
async def stream_run(run_id: str, request: Request) -> StreamingResponse:
    """SSE stream of OrchestratorEvents. Closes after run_finished or if the
    client disconnects."""
    state = request.app.state.registry.get(run_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"unknown run_id: {run_id!r}")

    async def event_source() -> AsyncIterator[bytes]:
        while True:
            if await request.is_disconnected():
                return
            try:
                # Short timeout so we revisit the disconnect check periodically
                # — without it a stalled client would pin a worker forever.
                event = await asyncio.wait_for(state.events.get(), timeout=1.0)
            except TimeoutError:
                if state.completed.is_set() and state.events.empty():
                    return
                # heartbeat keeps proxies from buffering/dropping the connection
                yield b": heartbeat\n\n"
                continue
            yield _format_sse(event)
            if event.kind == "run_finished":
                return

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # tell nginx not to buffer SSE
        },
    )


def _format_sse(event: OrchestratorEvent) -> bytes:
    payload = event.model_dump_json()
    return f"event: {event.kind}\ndata: {payload}\n\n".encode()
