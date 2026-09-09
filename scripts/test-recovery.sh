#!/usr/bin/env sh
# Destructive service-restart and logical backup/restore proof on an isolated database.
set -eu
cd "$(dirname "$0")/.."
export BACKEND_IMAGE="${BACKEND_IMAGE:-mad-devs-note-taker-backend:qa-evidence}"
export COMPOSE_PROJECT_NAME="${QA_RECOVERY_COMPOSE_PROJECT_NAME:-notetaker-qa-recovery-$$}"
docker compose build backend
db="${QA_RECOVERY_DATABASE_NAME:-notetaker_qa_recovery}"
url="postgresql+asyncpg://notetaker:notetaker@postgres:5432/$db"
backup="$(mktemp)"
cleanup() {
  rm -f "$backup"
  docker compose down -v >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker compose up -d --wait postgres redis
docker compose exec -T postgres dropdb -U notetaker --if-exists "$db"
docker compose exec -T postgres createdb -U notetaker "$db"
docker compose run --rm --no-deps -e DATABASE_URL="$url" backend uv run --frozen alembic upgrade head
docker compose exec -T postgres psql -U notetaker -d "$db" -v ON_ERROR_STOP=1 -c "INSERT INTO notes(id,title,body,starts_at,active,version) VALUES ('00000000-0000-0000-0000-00000000aa01','restart sentinel','',now(),true,1)"
docker compose exec -T redis redis-cli SET qa:restart:sentinel retained >/dev/null
docker compose restart postgres redis
docker compose up -d --wait postgres redis
test "$(docker compose exec -T postgres psql -U notetaker -d "$db" -Atc "SELECT title FROM notes WHERE id='00000000-0000-0000-0000-00000000aa01'")" = "restart sentinel"
test "$(docker compose exec -T redis redis-cli GET qa:restart:sentinel)" = "retained"
# Logical restore is tested separately from volume persistence.
docker compose exec -T postgres pg_dump -U notetaker -d "$db" --clean --if-exists --no-owner > "$backup"
docker compose exec -T postgres dropdb -U notetaker "$db"
docker compose exec -T postgres createdb -U notetaker "$db"
docker compose exec -T postgres psql -U notetaker -d "$db" -v ON_ERROR_STOP=1 < "$backup" >/dev/null
test "$(docker compose exec -T postgres psql -U notetaker -d "$db" -Atc "SELECT count(*) FROM notes")" = 1
echo "PASS: PostgreSQL/Redis restart persistence and PostgreSQL logical restore"
