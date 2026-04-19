-- Per-leaf verdicts. check_id is the content-hash node id from the compiler
-- (#6); doc_id is denormalised from runs so the cross-run cache lookup is a
-- single-table query: WHERE check_id = ? AND doc_id = ? LIMIT 1.
--
-- Multiple findings rows can share (check_id, doc_id) — one per run that
-- evaluated that leaf against that doc. The cache picks the most recent.
CREATE TABLE IF NOT EXISTS findings (
    run_id       UUID NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
    check_id     TEXT NOT NULL,
    doc_id       TEXT NOT NULL,
    passed       BOOLEAN NOT NULL,
    evidence     TEXT,
    page_ref     INT,
    confidence   REAL NOT NULL,
    -- clock_timestamp() (not now()) so two findings inserted in the same
    -- transaction get distinct timestamps. The cache lookup orders by this.
    created_at   TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, check_id)
);

-- The cache lookup index — by far the hottest query in the system once the
-- demo runs more than once. Order matters: check_id selects far more
-- aggressively than doc_id, so it leads.
CREATE INDEX IF NOT EXISTS findings_cache_idx
    ON findings (check_id, doc_id, created_at DESC);
