-- Per-LLM-call observability. Populated by the router (instrumentation is
-- ticket #11, deferred — table ships now so the schema is locked and
-- post-#14 work doesn't need another migration).
CREATE TABLE IF NOT EXISTS router_calls (
    id           BIGSERIAL PRIMARY KEY,
    run_id       UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    check_id     TEXT NOT NULL,
    provider     TEXT NOT NULL,
    tokens_in    INT NOT NULL,
    tokens_out   INT NOT NULL,
    cost_usd     NUMERIC(10, 6),
    latency_ms   INT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS router_calls_run_idx ON router_calls (run_id);
