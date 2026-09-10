#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
export BACKEND_IMAGE="${BACKEND_IMAGE:-mad-devs-note-taker-backend:qa-evidence}"
export COMPOSE_PROJECT_NAME="${QA_COMPOSE_PROJECT_NAME:-notetaker-qa-$$}"
export MAILPIT_UI_PORT="${QA_MAILPIT_UI_PORT:-0}"
docker compose build backend
qa_db="${QA_DATABASE_NAME:-notetaker_qa}"
qa_url="postgresql+asyncpg://notetaker:notetaker@postgres:5432/$qa_db"
worker_name="mad-devs-note-taker-qa-worker-$$"
plans="${QA_PLAN_OUTPUT:-/tmp/notetaker-qa-query-plans.json}"
plan_dir="$(mktemp -d)"
chmod 777 "$plan_dir"
cleanup() {
  rm -rf "$plan_dir"
  docker rm -f "$worker_name" >/dev/null 2>&1 || true
  docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose up -d --wait postgres redis mailpit
docker compose exec -T postgres dropdb -U notetaker --if-exists "$qa_db"
docker compose exec -T postgres createdb -U notetaker "$qa_db"
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic upgrade 0001
# Historical boundary: lifecycle columns must not leak backward from current models.
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc "SELECT count(*) FROM information_schema.columns WHERE table_name='notes' AND column_name IN ('superseded_at','series_trashed_at','purged_at','current_recurring_trash_action_id')")" = 0
# Reversible historical migrations retain their upgrade/downgrade coverage.
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic upgrade 0003_background
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic downgrade 0001
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic upgrade 0003_background
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic downgrade base
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic upgrade 0003_background
# The full-outage storage cutover is intentionally activation-irreversible.
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic upgrade head
if docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend \
  uv run --frozen alembic downgrade 0003_background >/dev/null 2>&1; then
  echo "0004_storage_contract downgrade unexpectedly succeeded" >&2
  exit 1
fi
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc 'SELECT version_num FROM alembic_version')" = 0004_storage_contract
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic check
# A separately managed worker proves tasks cross a real Redis broker/process boundary.
docker compose run -d --name "$worker_name" --no-deps   -e DATABASE_URL="$qa_url" -e REDIS_URL=redis://redis:6379/14   -e CELERY_BROKER_URL=redis://redis:6379/15 worker >/dev/null
# Wait for this exact worker rather than relying on Compose's development worker.
i=0
until docker exec "$worker_name" uv run --frozen celery -A app.jobs.celery_app:celery_app inspect ping --timeout 2 2>/dev/null | grep -q pong; do
  i=$((i + 1)); [ "$i" -lt 30 ] || { docker logs "$worker_name"; exit 1; }
done

docker compose run --rm --no-deps   -e TEST_DATABASE_URL="$qa_url" -e DATABASE_URL="$qa_url"   -e REDIS_URL=redis://redis:6379/14 -e CELERY_BROKER_URL=redis://redis:6379/15   -e SMTP_HOST=mailpit -e SMTP_PORT=1025 -e MAILPIT_API_URL=http://mailpit:8025   -e RUN_CELERY_INTEGRATION=1 -e FAIL_ON_SKIP=1 backend   uv run --frozen pytest -m 'postgres or runtime or celery' "$@"

mkdir -p "$(dirname "$plans")"
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" -v "$plan_dir:/qa-evidence" backend \
  uv run --frozen python scripts/qa_dataset.py --output /qa-evidence/query-plans.json
cp "$plan_dir/query-plans.json" "$plans"
echo "query-plan JSON retained at $plans"
