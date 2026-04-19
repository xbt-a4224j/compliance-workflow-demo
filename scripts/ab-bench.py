#!/usr/bin/env python3
"""A/B benchmark: fire N runs per provider, read orchestrator.run durations
from Jaeger's HTTP API, print a p50 / p95 / mean / stdev table + a one-line
verdict. Optional --out writes a matplotlib box plot.

Usage:
    uv run scripts/ab-bench.py --n 10 --doc synth_fund_01
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API = "http://localhost:8765"
JAEGER = "http://localhost:16686"
PROVIDERS = ("anthropic", "openai")
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "outputs"

AUTH_TOKEN = os.environ.get("AUTH_TOKEN", "").strip()
if not AUTH_TOKEN:
    sys.exit(
        "[bench] AUTH_TOKEN is unset — the API requires a bearer token on every "
        "request. Set AUTH_TOKEN in .env (same value the frontend prompts for)."
    )
AUTH_HEADER = {"Authorization": f"Bearer {AUTH_TOKEN}"}


def post_run(doc: str, primary: str) -> tuple[str, str]:
    body = json.dumps({"doc_id": doc, "primary": primary}).encode()
    req = urllib.request.Request(
        f"{API}/runs",
        data=body,
        headers={"Content-Type": "application/json", **AUTH_HEADER},
        method="POST",
    )
    with urllib.request.urlopen(req) as r:
        d = json.load(r)
    return d["run_id"], d["trace_id"]


def wait_for_run(run_id: str, timeout: float = 180.0) -> None:
    """Poll GET /runs/{id} until `result` is populated — i.e., orchestrator
    finished. Backend runs tasks concurrently, so the wall-clock wait here is
    the slowest task in the batch, not the sum."""
    deadline = time.time() + timeout
    req = urllib.request.Request(f"{API}/runs/{run_id}", headers=AUTH_HEADER)
    while time.time() < deadline:
        with urllib.request.urlopen(req) as r:
            d = json.load(r)
        if d.get("result") is not None:
            return
        time.sleep(0.5)
    raise TimeoutError(f"run {run_id} did not complete within {timeout}s")


def fetch_duration_ms(trace_id: str) -> float | None:
    """Pull the orchestrator.run span duration (μs) from Jaeger, return ms."""
    try:
        with urllib.request.urlopen(f"{JAEGER}/api/traces/{trace_id}") as r:
            d = json.load(r)
    except urllib.error.HTTPError:
        return None
    if not d.get("data"):
        return None
    trace = d["data"][0]
    for span in trace["spans"]:
        if span["operationName"] == "orchestrator.run":
            return span["duration"] / 1000
    return None


def summarize(durations: list[float]) -> dict[str, float | int]:
    if not durations:
        return {"n": 0}
    xs = sorted(durations)
    p95_idx = max(0, int(round(0.95 * (len(xs) - 1))))
    return {
        "n": len(xs),
        "p50": statistics.median(xs),
        "p95": xs[p95_idx],
        "mean": statistics.mean(xs),
        "stdev": statistics.stdev(xs) if len(xs) > 1 else 0.0,
    }


def write_chart(
    durations: dict[str, list[float]], doc: str, n: int, out_path: Path
) -> None:
    """Box plot per provider — requires matplotlib (dev dep)."""
    import matplotlib.pyplot as plt  # local import: optional dep

    providers = [p for p in PROVIDERS if durations.get(p)]
    data = [durations[p] for p in providers]

    fig, ax = plt.subplots(figsize=(7, 4.5))
    ax.boxplot(data, tick_labels=providers, showmeans=True,
               meanprops=dict(marker="D", markerfacecolor="#2563eb", markeredgecolor="#2563eb"))
    ax.set_ylabel("orchestrator.run duration (ms)")
    ax.set_title(f"A/B: {doc}  ·  n={n} per provider  ·  ♦ = mean")
    ax.grid(axis="y", linestyle=":", alpha=0.5)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n", type=int, default=10, help="runs per provider (default 10)")
    ap.add_argument("--doc", default="synth_fund_01", help="doc stem to run against")
    ap.add_argument("--flush-wait", type=int, default=15,
                    help="seconds to wait after all runs complete, for batch-span export")
    ap.add_argument("--out", type=Path, default=None,
                    help=f"PNG chart output path (default: {DEFAULT_OUT_DIR}/ab_<timestamp>.png)")
    ap.add_argument("--no-chart", action="store_true", help="skip the PNG chart")
    args = ap.parse_args()

    trace_ids: dict[str, list[str]] = defaultdict(list)
    run_ids: dict[str, list[str]] = defaultdict(list)

    print(f"[bench] firing {args.n} runs × {len(PROVIDERS)} providers against doc={args.doc}")
    for provider in PROVIDERS:
        for i in range(args.n):
            rid, tid = post_run(args.doc, provider)
            trace_ids[provider].append(tid)
            run_ids[provider].append(rid)
            print(f"  [{provider:>9} {i+1:>2}/{args.n}] run={rid[:8]}  trace={tid[:12]}")

    total = args.n * len(PROVIDERS)
    print(f"[bench] waiting for all {total} runs to complete (backend runs them concurrently)…")
    start = time.time()
    for provider in PROVIDERS:
        for rid in run_ids[provider]:
            wait_for_run(rid)
    print(f"[bench]   all done in {time.time() - start:.1f}s")

    print(f"[bench] sleeping {args.flush_wait}s for batch-span exporter to flush to Jaeger…")
    time.sleep(args.flush_wait)

    print(f"[bench] querying Jaeger for orchestrator.run durations…")
    durations: dict[str, list[float]] = {}
    for provider in PROVIDERS:
        ds = [d for d in (fetch_duration_ms(t) for t in trace_ids[provider]) if d is not None]
        durations[provider] = ds
        if len(ds) < len(trace_ids[provider]):
            print(f"  ({len(trace_ids[provider]) - len(ds)} {provider} traces not yet visible — try --flush-wait higher)")

    print()
    print(f"{'provider':<12} {'n':>3} {'p50':>9} {'p95':>9} {'mean':>9} {'stdev':>9}")
    print("-" * 54)
    summaries: dict[str, dict] = {}
    for provider in PROVIDERS:
        s = summarize(durations[provider])
        summaries[provider] = s
        if s["n"] == 0:
            print(f"{provider:<12} {'0':>3} (no traces)")
            continue
        print(f"{provider:<12} {s['n']:>3} {s['p50']:>7.0f}ms {s['p95']:>7.0f}ms {s['mean']:>7.0f}ms {s['stdev']:>7.0f}ms")

    a, o = summaries["anthropic"], summaries["openai"]
    if a.get("n") and o.get("n"):
        faster, slower = ("anthropic", "openai") if a["mean"] < o["mean"] else ("openai", "anthropic")
        fmean = summaries[faster]["mean"]
        smean = summaries[slower]["mean"]
        diff = smean - fmean
        pct = 100 * diff / smean
        print()
        print(f"→ {faster} is {diff:.0f}ms faster on mean ({pct:.0f}%) over n={a['n']}+{o['n']} samples")

    print()
    print(f"[bench] in Jaeger Search, filter  Service=compliance-workflow-demo  Tags=run.primary=<provider>")

    if not args.no_chart:
        out_path = args.out or DEFAULT_OUT_DIR / f"ab_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            write_chart(durations, args.doc, args.n, out_path)
            print(f"[bench] chart → {out_path}")
        except ImportError:
            print("[bench] matplotlib not installed — skipping chart. `uv sync --group dev` to enable.")


if __name__ == "__main__":
    main()
