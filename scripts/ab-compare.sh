#!/usr/bin/env bash
# Fire two runs against the same doc — one with Anthropic primary, one with
# OpenAI primary — wait for both to flush to Jaeger, then print a Compare URL.
# Paste into a browser: Jaeger's Compare view loads both pre-populated so you
# can eyeball "which provider served this faster."
#
# Usage:  scripts/ab-compare.sh [doc_id]
#         doc_id defaults to synth_fund_01 (see `curl :8765/docs` for the list)

set -euo pipefail

DOC="${1:-synth_fund_01}"
API="${API:-http://localhost:8765}"
JAEGER="${JAEGER:-http://localhost:16686}"
FLUSH_WAIT="${FLUSH_WAIT:-12}"

curl_run() {
  local primary="$1"
  curl -fsS -X POST "$API/runs" \
    -H 'Content-Type: application/json' \
    -d "{\"doc_id\":\"$DOC\",\"primary\":\"$primary\"}" \
    | python3 -c 'import sys,json;print(json.load(sys.stdin)["trace_id"])'
}

echo "[ab] doc=$DOC  posting anthropic-primary run…"
A=$(curl_run anthropic)
echo "[ab]   anthropic: $A"

echo "[ab] posting openai-primary run…"
B=$(curl_run openai)
echo "[ab]   openai:    $B"

echo "[ab] waiting ${FLUSH_WAIT}s for batch-span exporter to flush…"
sleep "$FLUSH_WAIT"

echo ""
echo "[ab] Compare URL:"
echo "     $JAEGER/trace/$A...$B"
