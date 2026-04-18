#!/usr/bin/env bash
# Bring the stack down and back up, then verify every service responds.
# Extend the CHECKS array as new services come online.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

COMPOSE="docker compose -f infra/docker-compose.yml"

# name|url|timeout_seconds
CHECKS=(
  "jaeger-ui|http://localhost:16686/|30"
)

echo "[smoke] stopping stack"
$COMPOSE down --remove-orphans

echo "[smoke] starting stack (waits on service healthchecks)"
$COMPOSE up -d --wait

for entry in "${CHECKS[@]}"; do
  IFS='|' read -r name url timeout <<<"$entry"
  echo "[smoke] waiting for ${name} (${url}, ${timeout}s)"
  deadline=$((SECONDS + timeout))
  until curl -fsS -o /dev/null "$url"; do
    if (( SECONDS >= deadline )); then
      echo "[smoke] FAIL: ${name} did not respond within ${timeout}s"
      $COMPOSE logs --tail=50
      exit 1
    fi
    sleep 1
  done
  echo "[smoke] OK: ${name}"
done

echo "[smoke] emitting test spans through OTLP pipeline"
(cd backend && uv run python scripts/otel_smoke.py)

echo "[smoke] verifying spans visible in jaeger (compliance-workflow-demo-smoke service)"
deadline=$((SECONDS + 15))
until curl -fsS http://localhost:16686/api/services | grep -q "compliance-workflow-demo-smoke"; do
  if (( SECONDS >= deadline )); then
    echo "[smoke] FAIL: compliance-workflow-demo-smoke service did not appear in jaeger within 15s"
    exit 1
  fi
  sleep 1
done
echo "[smoke] OK: spans reached jaeger"

echo "[smoke] all checks passed"
