# Design

Short record of the non-obvious decisions and what was deliberately left out.

## 1. Atomic LLM checks, not prompt-the-whole-rule

Compliance rules aren't one yes/no question. *"Past performance must include disclaimer"* is at least:

- is past performance mentioned at all?
- if so, is a disclaimer present?
- if so, is the disclaimer close enough to the reference to satisfy the "in conjunction with" clause?

Prompting the whole thing to a frontier model gets you a confident paragraph with no verdict to audit. So the DSL is a tree of **atomic** checks (each a single boolean + evidence), and the aggregators (`ALL_OF` / `ANY_OF`) are pure functions. The LLM never sees the aggregation logic. Trade-off: more tokens per rule. Win: every verdict has a grounded quote + page ref, and the aggregator is deterministic.

## 2. Content-addressed node IDs

Every node's ID is `sha256(canonical_json({op, params, sorted(child_ids)}))`, computed bottom-up. Implication: any leaf that's textually identical across rules collapses to one node. `(check_id, doc_id)` becomes a globally unique cache key, so re-running the same rule against the same doc is a DB lookup, not an LLM call. Trade-off: the IDs are opaque hex strings in logs. Win: caching and dedup both fall out for free.

## 3. Router nesting: failover → retry

```
for adapter in adapters:        # failover  (outer)
    async for attempt:          # retry     (inner)
        adapter.complete()
```

Retry handles "this call got unlucky, try again on the same provider." Failover wraps it: once retry exhausts on one provider, move to the next. PermanentError (4xx-shaped) skips both layers — bad config / bad request, never worth retrying or failing over.

## 4. In-process fan-out via `asyncio.gather`

The orchestrator schedules all leaves at once through `asyncio.gather`. v2 is the same `execute_check` behind a Redis queue + worker pool, swappable at `_fan_out_leaves`. Didn't build v2 because current scale doesn't justify the operational cost of a worker pool, and the seam is positioned so it's a 20-line change when it does. Trade-off: single-process ceiling. Win: no Redis dependency today, identical behavior semantics.

## 5. Page refs come from the chunker, not the LLM

LLMs hallucinate page numbers. The chunker stamps real pages onto every `DocChunk`, and `_resolve_page` matches the LLM's evidence quote back to a chunk to recover the page. If the quote doesn't match any chunk, `page_ref` is `None` — which is used as a hallucination guard for `FORBIDS_PHRASE`: a "not present" verdict without a groundable quote is flipped to "present," because the alternative is trusting an LLM's "I didn't find it but here's what it might have looked like" confabulation.

## 6. OpenTelemetry covers HTTP → LLM in one trace

FastAPIInstrumentor wraps every request. The orchestrator span is a child of the HTTP span (context propagates through `asyncio.create_task`). Each leaf gets its own span, each LLM attempt gets its own span inside the leaf. One `POST /runs` = one trace, typically 20+ spans, deep enough to answer "what happened" without crosschecking service logs. Trade-off: span cardinality scales with DAG size. Win: Jaeger Compare view + tag search cover the A/B analysis without a separate dashboard (see `scripts/ab-bench.py` for the "don't build a dashboard" move).

## 7. Best-effort DB persistence

Run persistence is wrapped in a try/except that logs and continues if Postgres is unreachable. Means the app works without `docker compose up`, and a DB blip doesn't poison the run result the UI already has via SSE. Trade-off: silent data loss on DB failure. Mitigation: for production you'd need a proper WAL + retry strategy; the demo accepts the loss.

## What was cut

- **Rule editor with save + validation + versioning** — the Rules tab is read-only. A real editor is three features (edit, validate, persist + version), each its own week.
- **Distributed orchestrator** — Redis queue + worker pool. Seam is in place; implementation is out of scope.
- **Per-provider circuit breaker** — removed. Was structurally non-functional because the Router is constructed per-request, so the failure counter reset every call (the breaker's whole point is cross-call state). A real implementation needs an app-state singleton; not worth the operational complexity at demo scale, and retry+failover already handle every failure mode you can demo without manually killing an LLM endpoint.
- **Metrics backend (Prometheus)** — the A/B story uses Jaeger's trace API as the analytics plane. Works at this scale; production would want metrics separate from traces.
- **Rule-level access control, signing, audit trail** — the "compliance" in the name is the *check*, not the governance around authoring. Both matter in real systems, neither is in scope here.
