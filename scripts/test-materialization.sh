#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export BACKEND_IMAGE="${BACKEND_IMAGE:-mad-devs-note-taker-backend:qa-evidence}"
export COMPOSE_PROJECT_NAME="${QA_MATERIALIZATION_COMPOSE_PROJECT_NAME:-notetaker-qa-materialization-$$}"
artifact_dir="${QA_MATERIALIZATION_ARTIFACT_DIR:-$PWD/docs/development/evidence}"
evidence_name="mad-devs-note-taker-materialization-evidence-$$"
cleanup() {
  docker rm -f "$evidence_name" >/dev/null 2>&1 || true
  docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

mkdir -p "$artifact_dir"
docker compose build backend
docker compose up -d --wait postgres
docker compose run --rm --no-deps backend uv run --frozen alembic upgrade head
MSYS2_ARG_CONV_EXCL=/tmp/task1-materialization.json docker compose run \
  --name "$evidence_name" --no-deps backend \
  uv run --frozen python scripts/benchmark_materialization.py \
  --runs 3 --output /tmp/task1-materialization.json
MSYS2_ARG_CONV_EXCL="$evidence_name:" docker cp \
  "$evidence_name:/tmp/task1-materialization.json" \
  "$artifact_dir/task1-materialization.json"
