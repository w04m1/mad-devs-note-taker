#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
[ "$#" -eq 1 ] || { echo "usage: $0 BACKUP.sql.gz" >&2; exit 2; }
[ -f "$1" ] || { echo "backup not found: $1" >&2; exit 2; }

python_bin=python3
command -v "$python_bin" >/dev/null 2>&1 || python_bin=python
docker_bin=${DOCKER_BIN:-docker}
"$python_bin" scripts/compose_db_target.py validate --require-running >/dev/null
database=$("$python_bin" scripts/compose_db_target.py database)
user=$("$python_bin" scripts/compose_db_target.py user)

umask 077
restore_sql=$(mktemp "${TMPDIR:-/tmp}/notetaker-restore.XXXXXX")
validation_database="notetaker_restore_validate_$$"
validation_created=0
writers_stopped=0
previously_running=""
cleanup() {
  status=$?
  if [ "$validation_created" -eq 1 ]; then
    "$docker_bin" compose exec -T postgres dropdb --username "$user" --if-exists \
      "$validation_database" >/dev/null 2>&1 || true
  fi
  rm -f "$restore_sql"
  if [ "$writers_stopped" -eq 1 ] && [ -n "$previously_running" ]; then
    # The target transaction rolls back on failure; restore precisely the prior service state.
    "$docker_bin" compose start $previously_running >/dev/null 2>&1 || true
  fi
  exit "$status"
}
trap cleanup EXIT INT TERM

# Fully consume and validate the archive before stopping ingress or touching the target database.
gzip -t "$1"
gzip -dc "$1" > "$restore_sql"
tail -n 12 "$restore_sql" | grep -q '^-- PostgreSQL database dump complete$'

expected_head=$("$docker_bin" compose run --rm --no-deps backend \
  uv run --frozen python -c \
  'from scripts.require_schema_head import expected_heads; heads=expected_heads(); assert len(heads) == 1; print(next(iter(heads)))')

# A disposable validation restore catches SQL failures and wrong-schema archives before outage.
"$docker_bin" compose exec -T postgres createdb --username "$user" "$validation_database"
validation_created=1
"$docker_bin" compose exec -T postgres psql --username "$user" --dbname "$validation_database" \
  --set ON_ERROR_STOP=on --single-transaction < "$restore_sql" >/dev/null
validation_head=$("$docker_bin" compose exec -T postgres psql --username "$user" \
  --dbname "$validation_database" --tuples-only --no-align \
  --command 'SELECT version_num FROM alembic_version')
[ "$validation_head" = "$expected_head" ] || {
  echo "backup schema $validation_head does not match expected head $expected_head" >&2
  exit 1
}
"$docker_bin" compose exec -T postgres dropdb --username "$user" "$validation_database" >/dev/null
validation_created=0

echo "This atomically replaces the $user@$database database. Type RESTORE to continue:"
answer=${RESTORE_CONFIRMATION:-}
if [ -z "$answer" ]; then
  read answer
fi
[ "$answer" = RESTORE ] || { echo "cancelled"; exit 1; }

for service in frontend backend worker beat; do
  if "$docker_bin" compose ps --services --filter status=running | grep -qx "$service"; then
    previously_running="$previously_running $service"
  fi
done
"$docker_bin" compose stop frontend backend worker beat >/dev/null
writers_stopped=1

# Refuse configuration drift and non-Compose connections before target mutation.
"$python_bin" scripts/compose_db_target.py validate --require-running >/dev/null
active_sessions=$("$docker_bin" compose exec -T postgres psql --username "$user" --dbname "$database" \
  --tuples-only --no-align --command \
  "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid()")
[ "$active_sessions" = 0 ] || {
  echo "restore refused: $active_sessions external database session(s) remain" >&2
  exit 1
}

# psql's single transaction makes every DROP/CREATE in the plain dump all-or-none.
"$docker_bin" compose exec -T postgres psql --username "$user" --dbname "$database" \
  --set ON_ERROR_STOP=on --single-transaction < "$restore_sql" >/dev/null
restored_head=$("$docker_bin" compose exec -T postgres psql --username "$user" --dbname "$database" \
  --tuples-only --no-align --command 'SELECT version_num FROM alembic_version')
[ "$restored_head" = "$expected_head" ] || {
  echo "restored schema $restored_head does not match expected head $expected_head" >&2
  exit 1
}

if [ -n "$previously_running" ]; then
  "$docker_bin" compose start $previously_running >/dev/null
fi
writers_stopped=0
rm -f "$restore_sql"
trap - EXIT INT TERM
echo "restore complete"
