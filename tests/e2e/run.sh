#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PROJECT="${E2E_COMPOSE_PROJECT:-notetaker-e2e}"
export E2E_COMPOSE_PROJECT="$PROJECT" E2E_BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:15173}" E2E_MAILPIT_PORT="${E2E_MAILPIT_PORT:-18025}"
export FRONTEND_PORT="${FRONTEND_PORT:-15173}" MAILPIT_UI_PORT="$E2E_MAILPIT_PORT"
cleanup() {
  code=$?
  if (( code != 0 )); then docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" ps || true; docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" logs --no-color --tail=200 > "$ROOT/tests/e2e/artifacts/compose.log" 2>&1 || true; fi
  if [[ "${E2E_KEEP_STACK:-0}" != "1" ]]; then docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" down --volumes --remove-orphans || true; fi
  exit "$code"
}
trap cleanup EXIT INT TERM
mkdir -p "$ROOT/tests/e2e/artifacts"
docker compose -p "$PROJECT" -f "$ROOT/compose.yaml" up --build --wait postgres redis mailpit migrate backend worker beat frontend
cd "$ROOT/tests/e2e"
corepack pnpm install --frozen-lockfile
corepack pnpm exec playwright install chromium
corepack pnpm run typecheck
corepack pnpm test "$@"
