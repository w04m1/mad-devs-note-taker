#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
[ "$#" -eq 1 ] || { echo "usage: $0 BACKUP.sql.gz" >&2; exit 2; }
[ -f "$1" ] || { echo "backup not found: $1" >&2; exit 2; }

echo "This replaces the ${POSTGRES_DB:-notetaker} database. Type RESTORE to continue:"
read answer
[ "$answer" = RESTORE ] || { echo "cancelled"; exit 1; }
docker compose stop backend worker beat
gzip -dc "$1" | docker compose exec -T postgres psql   --username "${POSTGRES_USER:-notetaker}"   --dbname "${POSTGRES_DB:-notetaker}"   --set ON_ERROR_STOP=on
docker compose up -d backend worker beat
echo "restore complete"
