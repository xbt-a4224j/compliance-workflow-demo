#!/usr/bin/env bash
# Stand up the full demo stack in one shot:
#   1. docker-compose infra (postgres + jaeger) — up if not already
#   2. FastAPI on :8765 with --reload
#   3. Vite dev server on :5173
#
# Ctrl-C tears down the app processes. Infra stays up for fast restarts —
# stop it with `docker compose -f infra/docker-compose.yml down`.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

COMPOSE="docker compose -f infra/docker-compose.yml"
API_PORT=8765
WEB_PORT=5173

if [[ ! -d frontend/node_modules ]]; then
  echo "[dev] installing frontend deps (first run only)"
  (cd frontend && npm install)
fi

echo "[dev] bringing up infra (postgres + jaeger)"
$COMPOSE up -d --wait

api_pid=""
web_pid=""
cleanup() {
  echo ""
  echo "[dev] stopping app processes (infra stays up — '$COMPOSE down' to stop it)"
  [[ -n "$api_pid" ]] && kill "$api_pid" 2>/dev/null || true
  [[ -n "$web_pid" ]] && kill "$web_pid" 2>/dev/null || true
  # Catch any orphaned children of the vite subshell.
  [[ -n "$web_pid" ]] && pkill -P "$web_pid" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "[dev] starting FastAPI on :${API_PORT}"
uv run uvicorn compliance_workflow_demo.api.app:app \
  --host 127.0.0.1 --port "$API_PORT" --reload &
api_pid=$!

echo "[dev] starting Vite on :${WEB_PORT}"
(cd frontend && npm run dev -- --port "$WEB_PORT") &
web_pid=$!

echo ""
echo "[dev] ready:"
echo "[dev]   app      → http://localhost:${WEB_PORT}"
echo "[dev]   api docs → http://localhost:${API_PORT}/api-docs"
echo "[dev]   jaeger   → http://localhost:16686"
echo "[dev] Ctrl-C to stop"
echo ""

wait
