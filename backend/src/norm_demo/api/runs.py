from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from compliance_workflow_demo.api.schemas import (
    CreateRunRequest,
    CreateRunResponse,
    GetRunResponse,
)
from compliance_workflow_demo.api.state import RunState
from compliance_workflow_demo.dsl import compile_rule
from compliance_workflow_demo.executor import Orchestrator
from compliance_workflow_demo.executor.run import OrchestratorEvent, RunResult

router = APIRouter()


@router.post("/runs", response_model=CreateRunResponse)
async def create_run(req: CreateRunRequest, request: Request) -> CreateRunResponse:
    """Compile the rule, kick off the orchestrator as a background task, and
    return run_id + DAG immediately so the UI can render pending tiles."""
    rules = request.app.state.rules
    docs = request.app.state.docs
    registry = request.app.state.registry
    llm_router = request.app.state.router

    rule = rules.get(req.rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"unknown rule_id: {req.rule_id!r}")
    doc = docs.get(req.doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail=f"unknown doc_id: {req.doc_id!r}")

    graph = compile_rule(rule)
    run_id = str(uuid.uuid4())
    state = RunState(run_id=run_id, rule_id=rule.id, doc_id=req.doc_id, dag=graph)

    async def on_event(event: OrchestratorEvent) -> None:
        await state.events.put(event)

    async def runner() -> RunResult:
        try:
            orch = Orchestrator(router=llm_router, on_event=on_event)
            result = await orch.run(graph, doc, run_id=run_id)
            state.result = result
            return result
        finally:
            state.completed.set()

    state.task = asyncio.create_task(runner())
    registry.add(state)

    return CreateRunResponse(run_id=run_id, dag=graph)


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
