"""Run every (rule, doc) cell of the violation matrix against live LLM(s).

Compares the orchestrator's verdict to the matrix in corpus/README.md and
prints PASS/FAIL per cell, plus a final summary. This is the falsifiable
"does the system actually work?" check — if any cell mismatches, either
the rule prompt, the doc content, or the LLM behavior is off.

Requires ANTHROPIC_API_KEY (and optionally OPENAI_API_KEY for failover).
With both set, Anthropic is primary; if it errors out, OpenAI catches.

Usage:
    uv run python scripts/verify_matrix.py            # parallel per doc
    uv run python scripts/verify_matrix.py --serial   # one cell at a time
                                                       # (workaround for #22, won't-fix)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from compliance_workflow_demo.dsl import Rule, compile_rule, load_rule  # noqa: E402
from compliance_workflow_demo.executor import Orchestrator  # noqa: E402
from compliance_workflow_demo.ingest import Document, parse_pdf_path  # noqa: E402
from compliance_workflow_demo.router import (  # noqa: E402
    AnthropicAdapter,
    OpenAIAdapter,
    ProviderAdapter,
    Router,
)

ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = ROOT / "rules"
CORPUS_DIR = ROOT / "corpus"

# Expected verdicts per corpus/README.md. True = the rule should pass on
# this doc; False = the rule should fail (i.e. a planted violation exists
# OR for the real prospectus, some clean compliant doc).
MATRIX: dict[str, dict[str, bool]] = {
    "PERF":   {"real_prospectus_01": True,
               "synth_fund_01": False, "synth_fund_02": True,  "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": True},
    "NOGUAR": {"real_prospectus_01": True,
               "synth_fund_01": True,  "synth_fund_02": False, "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": True},
    "BAL":    {"real_prospectus_01": True,
               "synth_fund_01": True,  "synth_fund_02": True,  "synth_fund_03": False,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": True},
    "FEES":   {"real_prospectus_01": True,
               "synth_fund_01": True,  "synth_fund_02": True,  "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": False, "synth_fund_06": True},
    # FWD: docs that report past performance now carry an FWD-specific
    # safe-harbor disclaimer (separate from the PERF past-perf disclaimer)
    # so the LLM doesn't read past-perf numbers as implicitly forward-looking.
    # synth_fund_02 still fails FWD because "guaranteed returns of 8%" IS a
    # forward-looking statement and no safe-harbor saves an explicit guarantee.
    # synth_fund_06 fails FWD because of the planted "we expect 18-22%" forecast.
    "FWD":    {"real_prospectus_01": True,
               "synth_fund_01": True,  "synth_fund_02": False, "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": False},
}


def _build_router() -> Router:
    adapters: list[ProviderAdapter] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        adapters.append(AnthropicAdapter())
    if os.environ.get("OPENAI_API_KEY"):
        adapters.append(OpenAIAdapter())
    if not adapters:
        raise SystemExit("set ANTHROPIC_API_KEY and/or OPENAI_API_KEY in .env")
    print(f"[router] {' → '.join(a.provider for a in adapters)}")
    return Router(adapters=adapters)


def _load_rules() -> dict[str, Rule]:
    rules: dict[str, Rule] = {}
    for path in sorted(RULES_DIR.glob("*.yaml")):
        rule = load_rule(path.read_text())
        rules[rule.id] = rule
    return rules


def _load_docs() -> dict[str, Document]:
    docs: dict[str, Document] = {}
    for path in sorted(CORPUS_DIR.glob("*.pdf")):
        docs[path.stem] = parse_pdf_path(path)
    return docs


async def _evaluate_cell(
    rule: Rule, doc: Document, router: Router
) -> tuple[bool, bool]:
    """Returns (actual_passed, errored)."""
    graph = compile_rule(rule)
    result = await Orchestrator(router=router).run(graph, doc)
    return result.per_rule[rule.id], result.per_rule_errored[rule.id]


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--serial",
        action="store_true",
        help=(
            "Run cells one at a time (slower; workaround for #22 "
            "noisy-neighbor flutter, won't-fix)"
        ),
    )
    args = parser.parse_args()

    router = _build_router()
    rules = _load_rules()
    docs = _load_docs()
    print(f"[mode] {'serial' if args.serial else 'parallel per doc'}")

    rule_ids = sorted(MATRIX.keys())
    doc_names = sorted({d for cells in MATRIX.values() for d in cells})
    # Restrict to docs that actually exist in the corpus dir.
    doc_names = [n for n in doc_names if n in docs]

    total_cells = len(rule_ids) * len(doc_names)
    print(f"\n{total_cells} cells to evaluate ({len(rule_ids)} rules × {len(doc_names)} docs)\n")

    # Header
    name_w = max(len(n) for n in doc_names) + 2
    print(f"{'doc':<{name_w}}" + "".join(f"{rid:<10}" for rid in rule_ids))
    print("-" * (name_w + 10 * len(rule_ids)))

    matches = 0
    mismatches: list[str] = []
    started = time.monotonic()

    for doc_name in doc_names:
        doc = docs[doc_name]
        if args.serial:
            outcomes = []
            for rid in rule_ids:
                outcomes.append(await _evaluate_cell(rules[rid], doc, router))
        else:
            # Run all rules for this doc concurrently — fewer wall-clock seconds.
            outcomes = await asyncio.gather(
                *[_evaluate_cell(rules[rid], doc, router) for rid in rule_ids]
            )
        cells = []
        for rid, (actual_pass, errored) in zip(rule_ids, outcomes, strict=True):
            expected = MATRIX[rid][doc_name]
            if errored:
                marker = "ERR"
                mismatches.append(f"{rid} × {doc_name}: errored during run")
            elif actual_pass == expected:
                marker = "ok" if expected else "ok!"  # ! = correctly caught a fail
                matches += 1
            else:
                marker = "MISS"
                mismatches.append(
                    f"{rid} × {doc_name}: expected {'PASS' if expected else 'FAIL'}, "
                    f"got {'PASS' if actual_pass else 'FAIL'}"
                )
            cells.append(f"{marker:<10}")
        print(f"{doc_name:<{name_w}}" + "".join(cells))

    elapsed = time.monotonic() - started
    print()
    print(f"{matches}/{total_cells} cells matched expectations ({elapsed:.1f}s wall clock)")
    if mismatches:
        print("\nMISMATCHES:")
        for m in mismatches:
            print(f"  - {m}")
        raise SystemExit(1)
    print("MATRIX HOLDS")


if __name__ == "__main__":
    asyncio.run(main())
