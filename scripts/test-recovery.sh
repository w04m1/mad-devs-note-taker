#!/usr/bin/env sh
# Destructive recovery/schema/Beat proof. Always uses a disposable Compose project and volumes.
set -eu
cd "$(dirname "$0")/.."

export BACKEND_IMAGE="${BACKEND_IMAGE:-mad-devs-note-taker-backend:qa-evidence}"
export COMPOSE_PROJECT_NAME="${QA_RECOVERY_COMPOSE_PROJECT_NAME:-notetaker-qa-recovery-$$}"
work_dir=$(mktemp -d)
env_file="$work_dir/compose.env"
database="notetaker_recovery_$$"
user="recovery_user"
password="recovery_password"
cat > "$env_file" <<EOF
POSTGRES_DB=$database
POSTGRES_USER=$user
POSTGRES_PASSWORD=$password
MAILPIT_UI_PORT=0
FRONTEND_PORT=0
BEAT_HEALTH_MAX_AGE_SECONDS=8
EOF
export COMPOSE_ENV_FILES="$env_file"
archive="$work_dir/valid.sql.gz"
cleanup() {
  chmod 700 "$work_dir" >/dev/null 2>&1 || true
  docker compose down -v >/dev/null 2>&1 || true
  rm -rf "$work_dir"
}
trap cleanup EXIT INT TERM

fail() { echo "FAIL: $*" >&2; exit 1; }
assert_title() {
  actual=$(docker compose exec -T postgres psql -U "$user" -d "$database" -Atc \
    "SELECT title FROM notes WHERE id='00000000-0000-0000-0000-00000000aa01'")
  [ "$actual" = "$1" ] || fail "expected title '$1', got '$actual'"
}
running_services() {
  docker compose ps --services --filter status=running | sort
}
wait_health() {
  service=$1 expected=$2 attempts=${3:-30} i=0
  container=$(docker compose ps -q "$service")
  while [ "$i" -lt "$attempts" ]; do
    state=$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container")
    [ "$state" = "$expected" ] && return 0
    i=$((i + 1))
    sleep 1
  done
  docker compose logs "$service" >&2
  fail "$service did not become $expected (last state: $state)"
}

chmod +x scripts/test-support/docker-fail-pgdump.sh scripts/test-support/gzip-fail.sh
docker compose build backend
docker compose up -d --wait postgres redis mailpit migrate backend beat
# Worker liveness is not part of this matrix; it is started to prove exact prior-state restore.
docker compose up -d worker

# The public script must honor .env-only user/database overrides.
test "$(python3 scripts/compose_db_target.py database)" = "$database"
test "$(python3 scripts/compose_db_target.py user)" = "$user"
docker compose exec -T postgres psql -U "$user" -d "$database" -v ON_ERROR_STOP=1 -c \
  "INSERT INTO notes(id,title,body,starts_at,active,version) VALUES ('00000000-0000-0000-0000-00000000aa01','backup sentinel','',now(),true,1)" >/dev/null

# Failed dump, compression, and destination creation never publish a final archive.
failed_dump="$work_dir/failed-dump.sql.gz"
if DOCKER_BIN="$PWD/scripts/test-support/docker-fail-pgdump.sh" sh scripts/backup.sh "$failed_dump"; then
  fail "injected pg_dump failure was reported as success"
fi
[ ! -e "$failed_dump" ] || fail "pg_dump failure published an archive"
failed_gzip="$work_dir/failed-gzip.sql.gz"
if GZIP_BIN="$PWD/scripts/test-support/gzip-fail.sh" sh scripts/backup.sh "$failed_gzip"; then
  fail "injected gzip failure was reported as success"
fi
[ ! -e "$failed_gzip" ] || fail "gzip failure published an archive"
mkdir "$work_dir/read-only"
chmod 500 "$work_dir/read-only"
if sh scripts/backup.sh "$work_dir/read-only/failure.sql.gz"; then
  fail "unwritable destination was reported as success"
fi
[ ! -e "$work_dir/read-only/failure.sql.gz" ] || fail "write failure published an archive"
chmod 700 "$work_dir/read-only"

sh scripts/backup.sh "$archive"
gzip -t "$archive"

# Corrupt/truncated and valid-gzip/mid-SQL archives fail before target mutation or service stop.
before_services=$(running_services)
head -c 128 "$archive" > "$work_dir/truncated.sql.gz"
if RESTORE_CONFIRMATION=RESTORE sh scripts/restore.sh "$work_dir/truncated.sql.gz"; then
  fail "truncated archive restored"
fi
assert_title "backup sentinel"
[ "$(running_services)" = "$before_services" ] || fail "truncated restore changed service state"
gzip -dc "$archive" > "$work_dir/mid-error.sql"
sed -i '/^-- PostgreSQL database dump complete$/i THIS IS DELIBERATELY INVALID SQL;' \
  "$work_dir/mid-error.sql"
gzip -c "$work_dir/mid-error.sql" > "$work_dir/mid-error.sql.gz"
if RESTORE_CONFIRMATION=RESTORE sh scripts/restore.sh "$work_dir/mid-error.sql.gz"; then
  fail "mid-SQL archive restored"
fi
assert_title "backup sentinel"
[ "$(running_services)" = "$before_services" ] || fail "mid-SQL restore changed service state"

# Configuration drift fails closed before ingress is stopped.
if RESTORE_CONFIRMATION=RESTORE DATABASE_URL='postgresql+asyncpg://wrong:wrong@postgres:5432/wrong' \
  sh scripts/restore.sh "$archive"; then
  fail "database target mismatch restored"
fi
[ "$(running_services)" = "$before_services" ] || fail "target mismatch changed service state"

# A valid archive replaces the target once and restores precisely the prior running set.
docker compose exec -T postgres psql -U "$user" -d "$database" -v ON_ERROR_STOP=1 -c \
  "UPDATE notes SET title='mutated after backup' WHERE id='00000000-0000-0000-0000-00000000aa01'" >/dev/null
RESTORE_CONFIRMATION=RESTORE sh scripts/restore.sh "$archive"
assert_title "backup sentinel"
[ "$(running_services)" = "$before_services" ] || fail "valid restore changed service state"

# Every writer's entrypoint admits exactly the image head and rejects missing, old, and ahead schemas.
head_url="postgresql+asyncpg://$user:$password@postgres:5432/$database"
docker compose run --rm --no-deps -e DATABASE_URL="$head_url" backend \
  sh /app/service-entrypoint.sh true
for candidate in missing old ahead; do
  docker compose exec -T postgres createdb -U "$user" "$database-$candidate"
done
old_url="postgresql+asyncpg://$user:$password@postgres:5432/$database-old"
docker compose run --rm --no-deps -e DATABASE_URL="$old_url" backend \
  uv run --frozen alembic upgrade 0003_background
ahead_url="postgresql+asyncpg://$user:$password@postgres:5432/$database-ahead"
docker compose run --rm --no-deps -e DATABASE_URL="$ahead_url" backend \
  uv run --frozen alembic upgrade head
docker compose exec -T postgres psql -U "$user" -d "$database-ahead" -v ON_ERROR_STOP=1 \
  -c "UPDATE alembic_version SET version_num='9999_ahead'" >/dev/null
for candidate in missing old ahead; do
  candidate_url="postgresql+asyncpg://$user:$password@postgres:5432/$database-$candidate"
  if docker compose run --rm --no-deps -e DATABASE_URL="$candidate_url" backend \
    sh /app/service-entrypoint.sh true; then
    fail "$candidate schema passed the writer gate"
  fi
done

# Beat owns the freshness signal: suspension and broker loss both become unhealthy,
# and a backend-local file cannot refresh Beat's container-local signal.
wait_health beat healthy 30
docker compose pause beat >/dev/null
docker compose exec -T backend sh -c 'touch /tmp/beat-published'
wait_health beat unhealthy 25
docker compose unpause beat >/dev/null
wait_health beat healthy 30
docker compose pause redis >/dev/null
wait_health beat unhealthy 25
docker compose unpause redis >/dev/null
wait_health redis healthy 30
wait_health beat healthy 45

echo "PASS: recovery atomicity, backup integrity, target selection, schema gate, and Beat health"
