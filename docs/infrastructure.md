# Local infrastructure and operations

## Prerequisites

- Docker Engine 27 or newer with Docker Compose v2.24 or newer. The Compose version is needed for `env_file.required` and long-form dependency conditions.
- At least 4 GB of free memory and 5 GB of free disk space.
- `curl` for the smoke script. `gzip` is also needed for backup and restore scripts.
- No host PostgreSQL, Redis, Python, or Node.js installation is required.

The application is an unauthenticated, single-profile local system. The default publications bind only to `127.0.0.1`.

## Integration assumptions

Infrastructure can be merged before the parallel application branches, but images only build after those branches provide their locked manifests.

- `backend/pyproject.toml` and `backend/uv.lock` exist. The importable ASGI application is `app.main:app`. Alembic uses `backend/alembic.ini`. The Celery instance is `app.jobs.celery_app:celery_app`.
- The backend exposes `GET /api/v1/health/live` and dependency-aware `GET /api/v1/health/ready`. Readiness may report Redis as degraded but must return 2xx while durable PostgreSQL writes remain safe.
- `frontend/package.json` and `frontend/pnpm-lock.yaml` exist and have `dev` and `build` scripts. The Vite server listens on the command-line host/port.
- `vite.config.ts` proxies both `/api` and `/ws` to `process.env.VITE_PROXY_TARGET` (`http://backend:8000` in Compose), with WebSocket proxying enabled for `/ws`. Browser code uses relative URLs and never sees Docker DNS names.
- Backend and frontend manifests are owned by their workstreams. The Dockerfiles copy either project tree wholesale, so normal root-level `app/`, `migrations/`, `src/`, and generated-file additions need no Dockerfile edit.

If an application workstream chooses different module or script names, update Compose and this contract in one focused integration commit.

## Start and inspect

No `.env` file is required. Defaults are embedded in Compose. To customize them:

```sh
cp .env.example .env
docker compose config --quiet
docker compose up --build --wait
docker compose ps
docker compose logs -f backend worker beat
```

Open the application at <http://localhost:5173> and captured email at <http://localhost:8025>. PostgreSQL and Redis have no host ports. Mailpit SMTP is internal only.

Startup is gated in this order:

1. PostgreSQL, Redis, and Mailpit become healthy.
2. The one-shot `migrate` container runs `alembic upgrade head` after PostgreSQL is healthy.
3. Backend, worker, and Beat cannot start if migration exits nonzero. Redis also gates processes that require it.
4. Frontend starts only after backend readiness succeeds.

`docker compose ps -a migrate` should show exit code 0. Exactly seven other services remain running.

## Routine commands

```sh
./scripts/compose-config.sh       # parse and normalize Compose
./scripts/smoke.sh                # build, start, wait, and probe the full stack
./scripts/test.sh                 # backend tests, optional frontend tests, frontend build
docker compose run --rm migrate  # apply new migrations explicitly
docker compose logs -f --tail=200 worker
docker compose restart backend worker beat
docker compose down              # stop containers and preserve named volumes
docker compose down --volumes    # destructive: delete database and Redis data
```

The smoke check verifies the frontend, proxied backend readiness, Mailpit API, the exact seven running service names, and successful migration completion. On failure it prints recent logs.

## Persistence and recovery

PostgreSQL stores authoritative application and reminder schedule state in `postgres_data`. Redis enables AOF with `appendfsync everysec` in `redis_data`. Redis recovery improves local continuity, but Redis is never the source of truth; scanners and the outbox recover work from PostgreSQL. Mailpit messages are disposable developer evidence and are not persisted.

Create and restore a logical PostgreSQL backup:

```sh
./scripts/backup.sh
./scripts/restore.sh backups/notetaker-YYYYMMDDTHHMMSSZ.sql.gz
```

The restore script stops state-writing application processes, requires typed confirmation, loads with `ON_ERROR_STOP`, and restarts them. Keep backups outside Docker volumes. For important data, test a restored copy before relying on it.

After downtime, due reminders inside the configured 60-second grace can run. Older deadlines become missed. Application code, not Redis AOF, enforces this rule.

## LAN testing

To test two physical devices, set these values in `.env`, replacing the example IP with the Docker host's LAN address:

```dotenv
FRONTEND_BIND_ADDRESS=0.0.0.0
ALLOWED_ORIGINS=http://192.168.1.50:5173
```

Then use `http://192.168.1.50:5173`. Do not expose Mailpit unless it is specifically needed. This mode has no authentication or TLS and is only suitable for a trusted temporary LAN. Never publish it to the internet.

## Troubleshooting

- **Migration blocks startup:** inspect `docker compose logs migrate postgres`, fix the migration, then run `docker compose up`. Never make backend processes apply migrations.
- **Frontend returns 502 or WebSockets fail:** confirm Vite uses `VITE_PROXY_TARGET` for both `/api` and `/ws`, and inspect backend readiness.
- **Worker is unhealthy:** `docker compose exec worker uv run --frozen celery -A app.jobs.celery_app:celery_app inspect ping` should return `pong`.
- **Beat is unhealthy:** inspect its logs and `/tmp/celerybeat.pid`. Only one Beat service is defined; do not scale it.
- **Reset local state:** first take a backup if needed, then run `docker compose down --volumes` and start again.
