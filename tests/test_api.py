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


_TEST_TOKEN = "test-token-xyz"
_AUTH_HEADER = {"Authorization": f"Bearer {_TEST_TOKEN}"}


@pytest.fixture(autouse=True)
def _env_setup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the lifespan to fall back to MockAdapter (no real-provider keys)
    and set a dummy AUTH_TOKEN so create_app doesn't refuse to start."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("AUTH_TOKEN", _TEST_TOKEN)


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
    """TestClient with the LLM router swapped for one that always passes, the
    bearer token attached, and DB wiring disabled (tests must not pick up
    cached findings from prior runs or local-dev activity)."""
    app = create_app()
    with TestClient(app, headers=_AUTH_HEADER) as c:
        _rtr = _passing_router()
        c.app.state.router = _rtr
        c.app.state.adapters = _rtr.adapters
        c.app.state.db_url = None  # force NoCache + skip persist_run
        yield c


# --- auth -----------------------------------------------------------------

def test_health_does_not_require_auth() -> None:
    """Probes and the UI's startup check hit /health before a token exists."""
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/health")
        assert r.status_code == 200


def test_protected_endpoint_401_without_token() -> None:
    app = create_app()
    with TestClient(app) as c:
        r = c.get("/rules")
        assert r.status_code == 401


def test_protected_endpoint_401_with_wrong_token() -> None:
    app = create_app()
    with TestClient(app, headers={"Authorization": "Bearer nope"}) as c:
        r = c.get("/rules")
        assert r.status_code == 401


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
    r = client.post("/runs", json={"rule_ids": ["PERF"], "doc_id": "synth_fund_01"})
    assert r.status_code == 200
    body = r.json()
    assert "run_id" in body
    assert len(body["run_id"]) == 36  # uuid4
    assert "dag" in body
    assert body["dag"]["roots"] == {"PERF": next(iter(body["dag"]["roots"].values()))}


def test_create_run_omitting_rule_ids_runs_every_rule(client: TestClient) -> None:
    """No rule_ids → evaluate the entire rule set in one DAG."""
    r = client.post("/runs", json={"doc_id": "synth_fund_04"})
    assert r.status_code == 200
    body = r.json()
    assert set(body["dag"]["roots"].keys()) == {"PERF", "NOGUAR", "BAL", "FEES", "FWD"}


def test_create_run_unknown_rule(client: TestClient) -> None:
    r = client.post(
        "/runs", json={"rule_ids": ["DOES_NOT_EXIST"], "doc_id": "synth_fund_01"}
    )
    assert r.status_code == 404
    assert "DOES_NOT_EXIST" in r.json()["detail"]


def test_create_run_unknown_doc(client: TestClient) -> None:
    r = client.post("/runs", json={"rule_ids": ["PERF"], "doc_id": "no_such_doc"})
    assert r.status_code == 404


def test_create_run_rejects_extra_fields(client: TestClient) -> None:
    r = client.post(
        "/runs",
        json={"rule_ids": ["PERF"], "doc_id": "synth_fund_01", "bogus": True},
    )
    assert r.status_code == 422  # pydantic extra="forbid" → unprocessable


# --- GET /runs/:id ---------------------------------------------------------

def test_get_run_404_for_unknown_id(client: TestClient) -> None:
    r = client.get("/runs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_get_run_returns_state_after_completion(client: TestClient) -> None:
    create = client.post("/runs", json={"rule_ids": ["PERF"], "doc_id": "synth_fund_01"})
    run_id = create.json()["run_id"]

    # Poll until complete (in-process orchestrator runs immediately under TestClient).
    for _ in range(50):
        r = client.get(f"/runs/{run_id}")
        assert r.status_code == 200
        if r.json()["result"] is not None:
            break
    body = r.json()
    assert body["run_id"] == run_id
    assert body["rule_id"] == "PERF"  # rule_label is comma-joined; single rule = its id
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
        AsyncClient(transport=transport, base_url="http://test", headers=_AUTH_HEADER) as ac,
        app.router.lifespan_context(app),
    ):
        _rtr = _passing_router()
        app.state.router = _rtr
        app.state.adapters = _rtr.adapters
        app.state.db_url = None

        create = await ac.post(
            "/runs", json={"rule_ids": ["NOGUAR"], "doc_id": "synth_fund_01"}
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
        AsyncClient(transport=transport, base_url="http://test", headers=_AUTH_HEADER) as ac,
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
        AsyncClient(transport=transport, base_url="http://test", headers=_AUTH_HEADER) as ac,
        app.router.lifespan_context(app),
    ):
            _rtr = _passing_router()
            app.state.router = _rtr
            app.state.adapters = _rtr.adapters
            app.state.db_url = None

            create = await ac.post(
                "/runs", json={"rule_ids": ["FEES"], "doc_id": "synth_fund_05"}
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
