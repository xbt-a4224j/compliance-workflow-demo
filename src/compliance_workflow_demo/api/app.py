from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from compliance_workflow_demo.api.resources import router as resources_router
from compliance_workflow_demo.api.runs import router as runs_router
from compliance_workflow_demo.api.state import RunRegistry
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


def _load_rules(directory: Path) -> dict[str, Rule]:
    return {
        rule.id: rule
        for rule in (load_rule(p.read_text()) for p in sorted(directory.glob("*.yaml")))
    }


def _load_docs(directory: Path) -> dict[str, Document]:
    return {p.stem: parse_pdf_path(p) for p in sorted(directory.glob("*.pdf"))}


def _build_router() -> Router:
    """Live providers if API keys are set, else MockAdapter so the API is
    runnable offline (e.g. for frontend dev without burning API credit)."""
    adapters: list[ProviderAdapter] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        adapters.append(AnthropicAdapter())
    if os.environ.get("OPENAI_API_KEY"):
        adapters.append(OpenAIAdapter())
    if not adapters:
        adapters.append(MockAdapter())
    return Router(adapters=adapters)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup loads everything into app.state; shutdown cancels in-flight runs."""
    rules_dir = Path(os.environ.get("RULES_DIR", DEFAULT_RULES_DIR))
    corpus_dir = Path(os.environ.get("CORPUS_DIR", DEFAULT_CORPUS_DIR))

    app.state.rules = _load_rules(rules_dir)
    app.state.docs = _load_docs(corpus_dir)
    app.state.router = _build_router()
    app.state.registry = RunRegistry()

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
    # Move Swagger UI off /docs so our GET /docs (corpus listing) wins.
    app = FastAPI(
        title="compliance-workflow-demo",
        lifespan=lifespan,
        docs_url="/api-docs",
        redoc_url="/api-redoc",
    )
    FastAPIInstrumentor.instrument_app(app)

    # Open CORS for the local Vite dev server (5173) and create-react-app
    # default (3000). Tightened in production; demo scope only.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://localhost:3000",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(runs_router)
    app.include_router(resources_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
