from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

import logging

from compliance_workflow_demo.api.auth import require_token
from compliance_workflow_demo.api.resources import router as resources_router
from compliance_workflow_demo.api.runs import router as runs_router
from compliance_workflow_demo.api.state import RunRegistry
from compliance_workflow_demo.db.connection import connect, database_url
from compliance_workflow_demo.db.migrate import apply_migrations
from compliance_workflow_demo.dsl import Rule, load_rule
from compliance_workflow_demo.ingest import Document, parse_pdf_path
from compliance_workflow_demo.obs.tracing import configure_tracing, force_flush
from compliance_workflow_demo.router import (
    AnthropicAdapter,
    MockAdapter,
    OpenAIAdapter,
    ProviderAdapter,
    Router,
)

# Repo conventions — kept here so the app can be launched from anywhere.
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_RULES_DIR = BACKEND_ROOT / "rules"
DEFAULT_CORPUS_DIR = BACKEND_ROOT / "corpus"


def _load_rules(directory: Path) -> tuple[dict[str, Rule], dict[str, str]]:
    """Return (rules_by_id, yaml_sources_by_id).  The sources let the Rules
    view in the UI show the authored YAML alongside the compiled DAG."""
    rules: dict[str, Rule] = {}
    sources: dict[str, str] = {}
    for path in sorted(directory.glob("*.yaml")):
        src = path.read_text()
        rule = load_rule(src)
        rules[rule.id] = rule
        sources[rule.id] = src
    return rules, sources


def _load_docs(directory: Path) -> dict[str, Document]:
    return {p.stem: parse_pdf_path(p) for p in sorted(directory.glob("*.pdf"))}


def _build_adapters() -> list[ProviderAdapter]:
    """Live providers if API keys are set, else MockAdapter so the API is
    runnable offline (e.g. for frontend dev without burning API credit)."""
    adapters: list[ProviderAdapter] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        adapters.append(AnthropicAdapter())
    if os.environ.get("OPENAI_API_KEY"):
        adapters.append(OpenAIAdapter())
    if not adapters:
        adapters.append(MockAdapter())
    return adapters


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup loads everything into app.state; shutdown cancels in-flight runs."""
    rules_dir = Path(os.environ.get("RULES_DIR", DEFAULT_RULES_DIR))
    corpus_dir = Path(os.environ.get("CORPUS_DIR", DEFAULT_CORPUS_DIR))

    adapters = _build_adapters()
    rules, rule_sources = _load_rules(rules_dir)
    app.state.rules = rules
    app.state.rule_sources = rule_sources
    app.state.docs = _load_docs(corpus_dir)
    app.state.adapters = adapters
    app.state.router = Router(adapters=list(adapters))
    app.state.registry = RunRegistry()

    # Best-effort DB setup: apply migrations, remember the URL so runners can
    # open per-run connections. If Postgres isn't reachable (demo running
    # without `docker compose up`), skip persistence entirely — the app still
    # works, DataGrip just has nothing to show.
    app.state.db_url = None
    try:
        conn = await connect()
        await apply_migrations(conn)
        await conn.close()
        app.state.db_url = database_url()
    except Exception as e:
        logging.getLogger(__name__).warning(
            "postgres unavailable — runs won't be persisted (%s)", e
        )

    yield

    # Best-effort: cancel any still-running orchestrator tasks so we don't leak
    # them on reload (uvicorn --reload triggers shutdown between reloads).
    for run_state in app.state.registry.all():
        if run_state.task is not None and not run_state.task.done():
            run_state.task.cancel()
    force_flush()


def create_app() -> FastAPI:
    # Load .env before anything reads os.environ — _build_router() at lifespan
    # startup reads ANTHROPIC_API_KEY / OPENAI_API_KEY to decide which adapters
    # to wire. Without this, keys that live only in .env are silently skipped.
    load_dotenv(BACKEND_ROOT / ".env")
    configure_tracing()

    # Auth is required. No escape hatch — refusing to start without
    # AUTH_TOKEN keeps the service from accidentally running open.
    auth_token = os.environ.get("AUTH_TOKEN", "").strip()
    if not auth_token:
        raise RuntimeError(
            "AUTH_TOKEN must be set in the environment (see .env.example). "
            "The API refuses to start without it."
        )

    # Move Swagger UI off /docs so our GET /docs (corpus listing) wins.
    app = FastAPI(
        title="compliance-workflow-demo",
        lifespan=lifespan,
        docs_url="/api-docs",
        redoc_url="/api-redoc",
    )
    app.state.auth_token = auth_token
    FastAPIInstrumentor.instrument_app(app)

    # CORS allowlist from CORS_ORIGINS (comma-separated) or the local-dev
    # defaults. Kept narrow — even the API docs + SSE stream come from here.
    cors_env = os.environ.get("CORS_ORIGINS", "").strip()
    allow_origins = (
        [o.strip() for o in cors_env.split(",") if o.strip()]
        if cors_env
        else [
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Both routers require the bearer token — /health stays open so probes
    # and the frontend's initial connectivity check don't trip auth.
    app.include_router(runs_router, dependencies=[Depends(require_token)])
    app.include_router(resources_router, dependencies=[Depends(require_token)])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
