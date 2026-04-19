from __future__ import annotations

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from compliance_workflow_demo.api.app import create_app
from compliance_workflow_demo.router import (
    CompletionRequest,
    CompletionResponse,
    MockAdapter,
    RetryPolicy,
    Router,
)


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the lifespan to fall back to MockAdapter — tests never hit a
    real provider regardless of whether the developer's shell has keys set."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def _passing_router() -> Router:
    """Mock router whose responses are valid LlmAnswer JSON, so the executor
    parses them as legitimate verdicts."""
    def responder(_req: CompletionRequest) -> CompletionResponse:
        return CompletionResponse(
            text=json.dumps({"passed": True, "evidence": None, "confidence": 0.99}),
            input_tokens=1, output_tokens=1, model="m", provider="mock",
        )

    return Router(
        adapters=[MockAdapter(responder=responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )


@pytest.fixture
def client():
    """TestClient with the LLM router swapped for one that always passes."""
    app = create_app()
    with TestClient(app) as c:
        c.app.state.router = _passing_router()
        yield c


# --- resource endpoints ----------------------------------------------------

def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_list_rules(client: TestClient) -> None:
    r = client.get("/rules")
    assert r.status_code == 200
    body = r.json()
    ids = {rule["id"] for rule in body}
    assert {"PERF", "NOGUAR", "BAL", "FEES", "FWD"} == ids
    for rule in body:
        assert rule["op"] in {"REQUIRES_CLAUSE", "ALL_OF", "ANY_OF"}


def test_list_docs(client: TestClient) -> None:
    r = client.get("/docs")
    assert r.status_code == 200
    body = r.json()
    ids = {doc["id"] for doc in body}
    # Synthetic docs are present; real_prospectus_01 is optional.
    assert {f"synth_fund_0{i}" for i in range(1, 7)} <= ids
    for doc in body:
        assert len(doc["sha256"]) == 64
        assert doc["pages"] >= 1


# --- POST /runs ------------------------------------------------------------

def test_create_run_returns_run_id_and_dag(client: TestClient) -> None:
    r = client.post("/runs", json={"rule_id": "PERF", "doc_id": "synth_fund_01"})
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert len(body["run_id"]) == 36  # uuid4
    assert "dag" in body
    assert body["dag"]["roots"] == {"PERF": next(iter(body["dag"]["roots"].values()))}


def test_create_run_unknown_rule(client: TestClient) -> None:
    r = client.post("/runs", json={"rule_id": "DOES_NOT_EXIST", "doc_id": "synth_fund_01"})
    assert r.status_code == 404
    assert "DOES_NOT_EXIST" in r.json()["detail"]


def test_create_run_unknown_doc(client: TestClient) -> None:
    r = client.post("/runs", json={"rule_id": "PERF", "doc_id": "no_such_doc"})
    assert r.status_code == 404


def test_create_run_rejects_extra_fields(client: TestClient) -> None:
    r = client.post(
        "/runs",
        json={"rule_id": "PERF", "doc_id": "synth_fund_01", "bogus": True},
    )
    assert r.status_code == 422  # pydantic extra="forbid" → unprocessable


# --- GET /runs/:id ---------------------------------------------------------

def test_get_run_404_for_unknown_id(client: TestClient) -> None:
    r = client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_get_run_returns_state_after_completion(client: TestClient) -> None:
    create = client.post("/runs", json={"rule_id": "PERF", "doc_id": "synth_fund_01"})
    run_id = create.json()["run_id"]

    # Poll until complete (in-process orchestrator runs immediately under TestClient).
    for _ in range(50):
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        if r.json()["result"] is not None:
            break
    body = r.json()
    assert body["run_id"] == run_id
    assert body["rule_id"] == "PERF"
    assert body["doc_id"] == "synth_fund_01"
    assert body["result"]["status"] == "passed"
    assert body["result"]["per_rule"] == {"PERF": True}


# --- SSE stream ------------------------------------------------------------

@pytest.mark.asyncio
async def test_sse_stream_emits_events_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    app = create_app()
    transport = ASGITransport(app=app)
    # Manually trigger lifespan startup — ASGITransport doesn't auto-run it.
    async with (
        AsyncClient(transport=transport, base_url="http://test") as ac,
        app.router.lifespan_context(app),
    ):
        app.state.router = _passing_router()

        create = await ac.post(
            "/runs", json={"rule_id": "NOGUAR", "doc_id": "synth_fund_01"}
        )
        run_id = create.json()["run_id"]

        kinds: list[str] = []
        async with ac.stream("GET", f"/runs/{run_id}/stream") as resp:
            assert resp.status_code == 200
            async for line in resp.aiter_lines():
                if line.startswith("event:"):
                    kinds.append(line.split(":", 1)[1].strip())
                    if kinds[-1] == "run_finished":
                        break
                if len(kinds) > 50:  # safety
                    break

    assert kinds[0] == "run_started"
    assert kinds[-1] == "run_finished"
    assert "check_started" in kinds
    assert "check_finished" in kinds


@pytest.mark.asyncio
async def test_sse_stream_404_for_unknown_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as ac,
        app.router.lifespan_context(app),
    ):
            r = await ac.get("/runs/nonexistent/stream")
            assert r.status_code == 404


# --- end-to-end: create + stream + final state ------------------------------

@pytest.mark.asyncio
async def test_end_to_end_run_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    """The full demo path: create a run, stream events, fetch final state."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    app = create_app()
    transport = ASGITransport(app=app)
    async with (
        AsyncClient(transport=transport, base_url="http://test") as ac,
        app.router.lifespan_context(app),
    ):
            app.state.router = _passing_router()

            create = await ac.post(
                "/runs", json={"rule_id": "FEES", "doc_id": "synth_fund_05"}
            )
            assert create.status_code == 200
            run_id = create.json()["run_id"]
            dag = create.json()["dag"]
            # FEES is ANY_OF over 2 leaves — 3 nodes total.
            assert len(dag["nodes"]) == 3

            # Wait for completion via /runs polling (the SSE path is covered above).
            for _ in range(30):
                r = await ac.get(f"/runs/{run_id}")
                if r.json()["result"] is not None:
                    break
                await asyncio.sleep(0.05)

            assert r.json()["result"]["status"] == "passed"
