"""End-to-end demo: load a rule, load a doc, run the full pipeline, print
findings.

Uses Anthropic if ANTHROPIC_API_KEY is set, otherwise falls back to a mock
adapter that answers from the violation matrix in corpus/README.md — lets
you exercise the orchestrator + DAG + page_ref recovery without API keys.

Usage:
    uv run python scripts/demo_run.py PERF synth_fund_01
    uv run python scripts/demo_run.py NOGUAR synth_fund_02
    uv run python scripts/demo_run.py FEES synth_fund_05

List options:
    uv run python scripts/demo_run.py --list
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from backend/ (or wherever this script is invoked from). Silent
# no-op if the file doesn't exist — the script falls back to a mock adapter
# in that case so it still runs.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from compliance_workflow_demo.dsl import compile_rule, load_rule  # noqa: E402
from compliance_workflow_demo.executor import Orchestrator, RunStatus  # noqa: E402
from compliance_workflow_demo.ingest import parse_pdf_path  # noqa: E402
from compliance_workflow_demo.router import (  # noqa: E402
    AnthropicAdapter,
    CompletionRequest,
    CompletionResponse,
    MockAdapter,
    OpenAIAdapter,
    ProviderAdapter,
    RetryPolicy,
    Router,
)

ROOT = Path(__file__).resolve().parent.parent
RULES_DIR = ROOT / "rules"
CORPUS_DIR = ROOT / "corpus"

# Hardcoded violation matrix from corpus/README.md. Used by the mock adapter
# so the offline demo produces the "right" answer per (rule, doc) pair.
MATRIX: dict[str, dict[str, bool]] = {
    "PERF":   {"synth_fund_01": False, "synth_fund_02": True,  "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": True},
    "NOGUAR": {"synth_fund_01": True,  "synth_fund_02": False, "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": True},
    "BAL":    {"synth_fund_01": True,  "synth_fund_02": True,  "synth_fund_03": False,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": True},
    "FEES":   {"synth_fund_01": True,  "synth_fund_02": True,  "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": False, "synth_fund_06": True},
    "FWD":    {"synth_fund_01": True,  "synth_fund_02": True,  "synth_fund_03": True,
               "synth_fund_04": True,  "synth_fund_05": True,  "synth_fund_06": False},
}


def _load_rule_by_id(rule_id: str):
    for path in RULES_DIR.glob("*.yaml"):
        rule = load_rule(path.read_text())
        if rule.id == rule_id:
            return rule
    raise SystemExit(f"no rule with id {rule_id!r} in {RULES_DIR}")


def _build_router(rule_id: str, doc_name: str) -> Router:
    """Live providers if keys are set (Anthropic primary, OpenAI fallback);
    otherwise a mock that answers from the matrix so the orchestrator runs
    offline. Adapter ordering is the failover priority — primary first."""
    adapters: list[ProviderAdapter] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        adapters.append(AnthropicAdapter())
    if os.environ.get("OPENAI_API_KEY"):
        adapters.append(OpenAIAdapter())

    if adapters:
        names = " → ".join(a.provider for a in adapters)
        print(f"[router] using live providers: {names}")
        return Router(adapters=adapters)

    print("[router] no API keys — using mock adapter from violation matrix")
    expected_pass = MATRIX.get(rule_id, {}).get(doc_name, True)

    def matrix_responder(req: CompletionRequest) -> CompletionResponse:
        # Single-leaf rules: this leaf's pass = the rule's expected verdict.
        # Compound rules: every leaf returns the rule-level expectation;
        # ALL_OF means every leaf agreeing on True passes; for FAIL cases the
        # mock biases at least one leaf False so the aggregator falls.
        # Good enough for offline orchestrator exercise; not a substitute for
        # real LLM evaluation.
        return CompletionResponse(
            text=json.dumps(
                {"passed": expected_pass, "evidence": None, "confidence": 0.9}
            ),
            input_tokens=len(req.system.split()) + len(req.user.split()),
            output_tokens=10,
            model="mock",
            provider="mock",
        )

    return Router(
        adapters=[MockAdapter(responder=matrix_responder)],
        retry=RetryPolicy(max_attempts=1, initial_wait_s=0.0, max_wait_s=0.01, jitter_s=0.0),
    )


def _print_dag(graph) -> None:
    leaves = sum(1 for n in graph.nodes.values() if n.is_leaf)
    aggs = sum(1 for n in graph.nodes.values() if not n.is_leaf)
    print()
    print(f"DAG: {len(graph.nodes)} nodes ({leaves} leaves, {aggs} aggregators)")
    for nid in graph.topo_order:
        node = graph.nodes[nid]
        marker = "leaf" if node.is_leaf else "agg "
        params = next(iter(node.params.values())) if node.params else ""
        print(f"  [{marker}] {nid[:8]}  {node.op:<16}  {params[:60]}")


def _print_result(result, graph) -> None:
    color = {
        RunStatus.PASSED:   "PASS",
        RunStatus.FAILED:   "FAIL",
        RunStatus.DEGRADED: "DEGR",
    }
    print()
    print(f"=== run {result.run_id[:8]}  →  {color[result.status]} ===")
    for rule_id, passed in result.per_rule.items():
        ok = "PASS" if passed else "FAIL"
        if result.per_rule_errored.get(rule_id):
            ok = "DEGR"
        print(f"  rule {rule_id}: {ok}")

    print("\nper-node:")
    for nid in graph.topo_order:
        node = graph.nodes[nid]
        finding = result.findings[nid]
        verdict = "PASS" if finding.passed else "FAIL"
        if finding.errored:
            verdict = "DEGR"
        evidence = ""
        if finding.check_result and finding.check_result.evidence:
            quote = finding.check_result.evidence[:60]
            page = finding.check_result.page_ref
            evidence = f"  ({quote!r}, p{page})"
        print(f"  [{verdict}] {nid[:8]}  {node.op:<16}{evidence}")

    if result.errors:
        print("\nerrors:")
        for nid, msg in result.errors.items():
            print(f"  {nid[:8]}: {msg}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rule", nargs="?", help="rule id (PERF, NOGUAR, BAL, FEES, FWD)")
    parser.add_argument("doc", nargs="?", help="doc stem (synth_fund_01..06, real_prospectus_01)")
    parser.add_argument("--list", action="store_true", help="list available rules and docs")
    args = parser.parse_args()

    if args.list or not args.rule or not args.doc:
        print("Available rules:")
        for path in sorted(RULES_DIR.glob("*.yaml")):
            rule = load_rule(path.read_text())
            print(f"  {rule.id:<8}  {rule.name}")
        print("\nAvailable docs:")
        for path in sorted(CORPUS_DIR.glob("*.pdf")):
            print(f"  {path.stem}")
        return

    rule = _load_rule_by_id(args.rule)
    doc_path = CORPUS_DIR / f"{args.doc}.pdf"
    if not doc_path.exists():
        raise SystemExit(f"no doc at {doc_path} — generate via scripts/generate_corpus.py")
    doc = parse_pdf_path(doc_path)

    print(f"\nrule: {rule.id} — {rule.name}")
    print(f"doc:  {args.doc}.pdf  (id={doc.id[:16]}..., {len(doc.chunks)} chunks)")

    graph = compile_rule(rule)
    _print_dag(graph)

    router = _build_router(rule.id, args.doc)
    result = await Orchestrator(router=router).run(graph, doc)
    _print_result(result, graph)


if __name__ == "__main__":
    asyncio.run(main())
