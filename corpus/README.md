# Corpus

Documents the rule engine evaluates against. **All PDFs in this directory are
inputs to the system, never outputs.**

| File | Origin |
|---|---|
| `real_prospectus_01.pdf` | **Placeholder — drop your own PDF here.** Should be a real published fund prospectus (filed with the SEC). The demo runs without it; the matrix row below assumes it passes every rule. |
| `synth_fund_01..06.pdf` | Synthetic fund marketing one-pagers, generated from `sources/synth_fund_NN.txt` via `scripts/generate_corpus.py`. Each is engineered to violate exactly one rule per the matrix below. |

## Violation matrix (the spec)

Rows are docs; columns are rules from `rules/`. Cells are the
**expected** verdict when that rule runs against that doc. The matrix is the
contract — if a real run diverges from it, either the rule, the doc, or the
evaluator is broken.

| Doc                  | PERF     | NOGUAR   | BAL      | FEES     | FWD      |
|----------------------|----------|----------|----------|----------|----------|
| real_prospectus_01   | pass     | pass     | pass     | pass     | pass     |
| synth_fund_01        | **FAIL** | pass     | pass     | pass     | pass     |
| synth_fund_02        | pass     | **FAIL** | pass     | pass     | **FAIL** |
| synth_fund_03        | pass     | pass     | **FAIL** | pass     | pass     |
| synth_fund_04        | pass     | pass     | pass     | pass     | pass     |
| synth_fund_05        | pass     | pass     | pass     | **FAIL** | pass     |
| synth_fund_06        | pass     | pass     | pass     | pass     | **FAIL** |

> `synth_fund_02` legitimately fails both `NOGUAR` (planted "guaranteed returns" assertion)
> and `FWD` (the same assertion is itself a forward-looking statement without safe-harbor —
> a single piece of bad copy can violate multiple rules, which is realistic).
>
> Synth docs that report past performance carry an explicit FWD-specific safe-harbor
> disclaimer in the "FORWARD-LOOKING STATEMENTS" section so the LLM doesn't read
> historical reporting as implicit forward-looking. The disclaimer wording is
> distinct from PERF's required phrasing — synth_fund_01 still fails PERF.

## Why the matrix matters

"My rule flagged something" is a meaningless demo. "My rule flagged the doc
because I planted exactly this violation on page N" is the demo. The matrix
makes every run falsifiable — every cell has a definite expected outcome
that an integration test (or a human watching the demo) can verify.

## Regenerating the synthetics

```bash
cd backend
uv run python scripts/generate_corpus.py
```

Edit `corpus/sources/synth_fund_NN.txt` to change content. The `{{PAGE_BREAK}}`
marker becomes a real PDF page break — page numbers in the matrix line up
with PDF page numbers via the chunker's per-page stamping.
