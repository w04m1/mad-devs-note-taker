#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."

# Start dependencies and apply the real schema once. Test commands use the same
# locked images as local development.
docker compose up -d --wait postgres redis mailpit
docker compose run --rm migrate
docker compose run --rm backend uv run --frozen pytest -m "not postgres and not runtime and not celery" "$@"
./scripts/test-postgres.sh "$@"
docker compose run --rm frontend pnpm run --if-present test
docker compose run --rm frontend pnpm build
