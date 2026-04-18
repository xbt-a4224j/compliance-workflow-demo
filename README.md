# compliance-workflow-demo

Compliance DSL + outage-resilient LLM router. A YAML rule compiles to a DAG of atomic LLM checks; every call goes through a router with per-provider circuit breakers, retries, and Anthropic → OpenAI failover. Traced end-to-end in OpenTelemetry.

Built for a (redacted) interview.

## Layout

```
backend/         Python 3.12, FastAPI, pydantic v2
  src/compliance_workflow_demo/
    dsl/        rule schema + compiler
    router/     provider adapters, breaker, retry, failover
    executor/   atomic check + orchestrator
    ingest/     PDF chunking, page-ref stamping
    api/        FastAPI endpoints (REST + SSE)
    obs/        OpenTelemetry setup
  rules/        FINRA 2210 rule YAMLs
  corpus/       SEC docs + synthetic fund one-pagers
  tests/
frontend/       Vite + React + TS
infra/          docker-compose (postgres, redis, jaeger)
```

## Quick start

TBD — see DEMO.md once it lands.
