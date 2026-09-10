#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."

python_bin=python3
command -v "$python_bin" >/dev/null 2>&1 || python_bin=python
docker_bin=${DOCKER_BIN:-docker}
gzip_bin=${GZIP_BIN:-gzip}
"$python_bin" scripts/compose_db_target.py validate --require-running >/dev/null
database=$("$python_bin" scripts/compose_db_target.py database)
user=$("$python_bin" scripts/compose_db_target.py user)

out="${1:-backups/$database-$(date -u +%Y%m%dT%H%M%SZ).sql.gz}"
out_dir=$(dirname "$out")
mkdir -p "$out_dir"
[ ! -e "$out" ] || { echo "backup already exists: $out" >&2; exit 2; }

umask 077
temporary_sql=$(mktemp "$out_dir/.notetaker-backup.XXXXXX")
temporary_archive="$temporary_sql.gz"
cleanup() {
  rm -f "$temporary_sql" "$temporary_archive"
}
trap cleanup EXIT INT TERM

"$docker_bin" compose exec -T postgres pg_dump \
  --username "$user" \
  --dbname "$database" \
  --clean --if-exists --no-owner > "$temporary_sql"
tail -n 12 "$temporary_sql" | grep -q '^-- PostgreSQL database dump complete$'
"$gzip_bin" -c "$temporary_sql" > "$temporary_archive"
"$gzip_bin" -t "$temporary_archive"
mv "$temporary_archive" "$out"
trap - EXIT INT TERM
rm -f "$temporary_sql"
echo "wrote validated backup $out"
