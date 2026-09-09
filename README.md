# Notetaker

Notetaker is a local, unauthenticated, single-profile note and reminder application. It has a React/TypeScript frontend, a FastAPI backend, PostgreSQL persistence, Redis/Celery background work and realtime invalidation, and Mailpit for local email capture.

See [implementation status](docs/implementation-status.md) for the current scope and known limits. See [verification](docs/verification.md) for evidence and the exact boundary of each check. `PLAN.md` is the design plan, not a record that every planned check passed.

## Start the complete stack

Prerequisites: Docker Engine 27+, Docker Compose v2.24+, at least 4 GB free memory and 5 GB free disk, and `curl`. No host Python, Node.js, PostgreSQL, or Redis install is required.

```sh
# Optional: override local defaults
cp .env.example .env

# Build, migrate, and wait for all services
./scripts/compose-config.sh
docker compose up --build --wait
```

Open the application at <http://localhost:5173> and Mailpit at <http://localhost:8025>. The migration is a one-shot eighth service. Seven long-lived services should remain healthy.

## Checks

```sh
./scripts/smoke.sh       # build/start; check seven services, migration, UI, API proxy, Mailpit API
./scripts/test.sh        # Compose-backed backend tests, frontend tests, frontend build

# Backend-only fast checks (database integration tests skip without TEST_DATABASE_URL)
cd backend
uv sync --frozen
uv run --frozen ruff check .
uv run --frozen pytest

# Frontend-only checks (Node >=22.13 and pnpm 11.21.0)
cd frontend
pnpm install --frozen-lockfile
pnpm test
pnpm build
pnpm dev                # proxies /api and /ws to localhost:8000 by default
```

`./scripts/smoke.sh` checks deployment wiring. It does not create a reminder or prove SMTP delivery. The recorded real Mailpit reminder check was manual; see [verification](docs/verification.md). The production frontend build currently emits a large-chunk warning.

## Operations

```sh
docker compose ps
docker compose logs -f --tail=200 backend worker beat
docker compose run --rm migrate
docker compose restart backend worker beat
docker compose down              # preserves PostgreSQL and Redis volumes
docker compose down --volumes    # destructive: deletes local application data
```

More detail, including configuration, backup/restore, LAN use, and troubleshooting, is in [local infrastructure and operations](docs/infrastructure.md).
