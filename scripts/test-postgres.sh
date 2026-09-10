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
evidence_name="mad-devs-note-taker-qa-evidence-$$"
plans="${QA_PLAN_OUTPUT:-/tmp/notetaker-qa-query-plans.json}"
cleanup() {
  docker rm -f "$worker_name" >/dev/null 2>&1 || true
  docker rm -f "$evidence_name" >/dev/null 2>&1 || true
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
# Seed legacy rows at the last reversible boundary so the storage cutover's
# repair behavior is proven independently of current ORM safeguards.
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U notetaker -d "$qa_db" <<'SQL'
INSERT INTO recurrence_series (
  id, lineage_id, local_start, timezone, rrule, end_date,
  template_title, template_body, template_active, version
) VALUES (
  '10000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  '2026-01-01 09:00:00', 'UTC', 'FREQ=DAILY', '2026-01-31',
  'legacy', '', true, 1
);
INSERT INTO notes (
  id, title, body, starts_at, active, deleted_at, series_id,
  recurrence_key, version, superseded_at
) VALUES
  (
    '20000000-0000-0000-0000-000000000001', 'ghost', '',
    '2026-01-02 09:00:00+00', true, NULL,
    '10000000-0000-0000-0000-000000000001',
    '2026-01-02 09:00:00+00', 1, '2026-02-01 12:00:00+00'
  ),
  (
    '20000000-0000-0000-0000-000000000002', 'ordinary deleted', '',
    '2026-01-03 09:00:00+00', true, '2026-02-02 12:00:00+00',
    '10000000-0000-0000-0000-000000000001',
    '2026-01-03 09:00:00+00', 1, NULL
  );
INSERT INTO occurrence_exceptions (
  id, series_id, recurrence_key, overridden_fields, cancelled
) VALUES (
  '30000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  '2026-01-02 09:00:00+00', '{"title":"false exception"}', false
);
INSERT INTO reminder_rules (
  id, note_id, offset_minutes, enabled, current_cycle_number
) VALUES (
  '40000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000001', 10, true, 1
);
INSERT INTO reminder_deliveries (
  id, reminder_rule_id, cycle_number, due_at, state
) VALUES (
  '50000000-0000-0000-0000-000000000001',
  '40000000-0000-0000-0000-000000000001', 1,
  '2026-01-02 08:50:00+00', 'pending'
);
SQL
# The full-outage storage cutover is intentionally activation-irreversible.
docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend uv run --frozen alembic upgrade head
if docker compose run --rm --no-deps -e DATABASE_URL="$qa_url" backend \
  uv run --frozen alembic downgrade 0003_background >/dev/null 2>&1; then
  echo "0004_storage_contract downgrade unexpectedly succeeded" >&2
  exit 1
fi
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc 'SELECT version_num FROM alembic_version')" = 0004_storage_contract
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc "SELECT deleted_at = superseded_at FROM notes WHERE id = '20000000-0000-0000-0000-000000000001'")" = t
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc "SELECT deleted_at = '2026-02-02 12:00:00+00'::timestamptz AND superseded_at IS NULL FROM notes WHERE id = '20000000-0000-0000-0000-000000000002'")" = t
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc "SELECT state = 'cancelled' AND result_at IS NOT NULL FROM reminder_deliveries WHERE id = '50000000-0000-0000-0000-000000000001'")" = t
test "$(docker compose exec -T postgres psql -U notetaker -d "$qa_db" -Atc "SELECT count(*) FROM occurrence_exceptions WHERE id = '30000000-0000-0000-0000-000000000001'")" = 0
# Prove a sealed action's identity and membership cannot be rewritten directly.
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U notetaker -d "$qa_db" <<'SQL'
BEGIN;
INSERT INTO recurring_trash_actions (
  id, series_id, boundary_recurrence_key, trashed_at
) VALUES (
  '60000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000001',
  '2026-01-03 09:00:00+00', '2026-02-02 12:00:00+00'
);
INSERT INTO recurring_trash_action_members (action_id, note_id) VALUES (
  '60000000-0000-0000-0000-000000000001',
  '20000000-0000-0000-0000-000000000002'
);
UPDATE notes SET current_recurring_trash_action_id =
  '60000000-0000-0000-0000-000000000001'
WHERE id = '20000000-0000-0000-0000-000000000002';
UPDATE recurring_trash_actions SET sealed_at = clock_timestamp()
WHERE id = '60000000-0000-0000-0000-000000000001';
COMMIT;
DO $$
DECLARE blocked boolean := false;
BEGIN
  BEGIN
    UPDATE recurring_trash_actions SET boundary_recurrence_key =
      '2026-01-04 09:00:00+00'
    WHERE id = '60000000-0000-0000-0000-000000000001';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%immutable%' THEN blocked := true; ELSE RAISE; END IF;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'sealed action identity mutation succeeded'; END IF;
END $$;
DO $$
DECLARE blocked boolean := false;
BEGIN
  BEGIN
    DELETE FROM recurring_trash_action_members
    WHERE action_id = '60000000-0000-0000-0000-000000000001';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM LIKE '%immutable%' THEN blocked := true; ELSE RAISE; END IF;
  END;
  IF NOT blocked THEN RAISE EXCEPTION 'sealed action membership deletion succeeded'; END IF;
END $$;
SQL
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
MSYS2_ARG_CONV_EXCL=/tmp/query-plans.json docker compose run --name "$evidence_name" --no-deps \
  -e DATABASE_URL="$qa_url" backend uv run --frozen python scripts/qa_dataset.py \
  --output /tmp/query-plans.json
MSYS2_ARG_CONV_EXCL="$evidence_name:" docker cp \
  "$evidence_name:/tmp/query-plans.json" "$plans"
echo "query-plan JSON retained at $plans"
