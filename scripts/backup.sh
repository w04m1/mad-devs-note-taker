#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
out="${1:-backups/notetaker-$(date -u +%Y%m%dT%H%M%SZ).sql.gz}"
mkdir -p "$(dirname "$out")"
docker compose exec -T postgres pg_dump   --username "${POSTGRES_USER:-notetaker}"   --dbname "${POSTGRES_DB:-notetaker}"   --clean --if-exists --no-owner | gzip > "$out"
echo "wrote $out"
