-- Per-run metadata. id is a UUID — each run is a distinct event with no
-- content to hash. doc_id is sha256(pdf_bytes) from the chunker (#15) so
-- joins to findings are stable.
CREATE TABLE IF NOT EXISTS runs (
    id           UUID PRIMARY KEY,
    rule_id      TEXT NOT NULL,
    doc_id       TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('running', 'passed', 'failed', 'degraded')),
    started_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS runs_started_at_idx ON runs (started_at DESC);
