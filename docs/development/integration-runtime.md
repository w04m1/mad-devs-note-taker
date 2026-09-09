# Integrated runtime decision log

## 2026-09-09 — Frozen environment names and database driver boundary

- **Problem or decision:** The merged backend settings used shortened names such as `DEFAULT_EMAIL` and `REMINDER_SCAN_SECONDS`, while Compose and the frozen section 13 contract provide `APP_DEFAULT_EMAIL` and `REMINDER_SCAN_INTERVAL_SECONDS`. Alembic also read a separate synchronous URL whose default host was `localhost`, so the migration container could not reach PostgreSQL at Compose DNS name `postgres`.
- **Chosen approach and reason:** Model every frozen environment name directly in `Settings`. Keep `DATABASE_URL` as the only public database variable and as the async HTTP URL. Derive `database_sync_url` from it by retaining credentials, host, port, database, and query while changing only the SQLAlchemy driver to `postgresql+psycopg`. Alembic and synchronous sessions therefore use the in-network endpoint without adding an environment variable outside the frozen contract.
- **Alternative and tradeoff:** Adding `DATABASE_SYNC_URL` to Compose would be explicit, but it would extend the frozen contract and allow the two endpoints to drift. Giving only the migration service a synchronous `DATABASE_URL` would make HTTP and migration configuration mean different things and would not fix future synchronous workers.
- **Evidence:** Unit tests load the exact frozen names and assert conversion of an async URL on host `postgres` to a psycopg URL. The real `0001` migration is run against PostgreSQL below.
- **Deviations or unresolved work:** `ALLOWED_ORIGINS` remains a string until HTTP CORS handling lands; this integration does not invent that missing feature.

## 2026-09-09 — Frontend proxy and locked toolchain alignment

- **Problem or decision:** Compose supplied `VITE_PROXY_TARGET`, but `vite.config.ts` ignored it and hard-coded Compose DNS. The frontend manifest requires `pnpm@11.21.0`, while its Dockerfile prepared pnpm 9.12.3 on Node 22.11.0. pnpm 11.21.0 rejects Node versions below 22.13.
- **Chosen approach and reason:** Read `VITE_PROXY_TARGET` for both HTTP and WebSocket proxy entries, with `http://localhost:8000` as the direct host-development fallback. Install the manifest-declared pnpm 11.21.0 exactly and pin Node 22.13.1, which satisfies pnpm's engine floor. Install pnpm with npm rather than the old bundled Corepack, whose signing-key set rejected the current pnpm package.
- **Alternative and tradeoff:** Retaining pnpm 9 makes the old image build but violates `packageManager`. Updating bundled Corepack would add a second tool-version pin and still offer no benefit over an exact global install. A floating Node 22 tag would work but would weaken reproducibility.
- **Evidence:** Baseline frontend build showed Corepack's missing signing key and then the corrected pnpm pin showed the Node `>=22.13` requirement. Final frozen image build and frontend build results are recorded below.
- **Deviations or unresolved work:** The image is a development Vite image, as planned; a separate production-serving image is outside this task.

## 2026-09-09 — Celery integration gate

- **Problem or decision:** Compose defines the required `worker` and `beat` commands, but merged backend code has neither a Celery dependency nor `app.jobs.celery_app`.
- **Chosen approach and reason:** Keep the intended topology and commands. Add a clear smoke preflight and operator documentation that block full-stack claims until both the locked dependency and real application module land. Do not create placeholder tasks or a fake Celery application.
- **Alternative and tradeoff:** Removing worker and Beat would make default startup appear healthy but violate the planned topology. Empty placeholder jobs would make orchestration green without implementing reminder/outbox behavior and would hide the missing product work.
- **Evidence:** `backend/uv.lock` has no Celery package and `backend/app/jobs/celery_app.py` does not exist. `./scripts/smoke.sh` exits 2 with a precise gate message.
- **Deviations or unresolved work:** Seven-long-lived-service smoke validation is blocked on the backend Celery workstream. Database, migration, backend tests, frontend build, and Compose validation remain independently testable.


## 2026-09-09 — Health probe exception boundary

- **Problem or decision:** The first integration lint command targeted `app`, `migrations`, and `tests`, so it missed `backend/docker-healthcheck.py`. The exact repository-wide Ruff check reported `BLE001` because the probe caught every `Exception`.
- **Chosen approach and reason:** Catch `OSError`, which covers `urllib.error.URLError`, `HTTPError`, socket errors, DNS failures, refused connections, and timeouts from this fixed HTTP probe. Let programming errors surface instead of converting them into a generic unhealthy result.
- **Alternative and tradeoff:** A `BLE001` suppression or continued broad catch would keep all failures mapped to unhealthy, but could hide defects in the probe itself. Listing `URLError`, `HTTPError`, and timeout classes separately is noisier because those URL exceptions already inherit from `OSError`.
- **Evidence:** Python runtime inheritance inspection confirms `URLError` and `HTTPError` derive from `OSError`. `cd backend && uv run --frozen ruff check .` and the locked backend test suite both pass after the narrow change.
- **Deviations or unresolved work:** None.

## Verification record

- `./scripts/compose-config.sh`: passed with all eight service definitions.
- `docker compose build backend`: passed with Python 3.12.7, uv 0.5.11, and `uv sync --frozen`.
- `docker compose build frontend`: passed with Node 22.13.1, pnpm 11.21.0, and `pnpm install --frozen-lockfile`.
- Backend locked pytest: 6 passed; two upstream Starlette/FastAPI deprecation warnings remain.
- Exact repository-wide backend lint, `cd backend && uv run --frozen ruff check .`: passed.
- Frontend Vitest: 12 passed across four files.
- Frontend production build: passed; Vite transformed 1,968 modules.
- PostgreSQL 16.4 became healthy and `docker compose run --rm migrate` applied revision `0001` using `PostgresqlImpl`.
- Schema inspection: `alembic_version=0001`, extension `pg_trgm` exists, and 13 public tables exist.
- Integrated subset startup (`postgres migrate backend frontend`, with Redis and Mailpit dependencies): passed; PostgreSQL, Redis, Mailpit, backend, and frontend were healthy and migrate exited 0.
- Frontend root and proxied `/api/v1/health/ready`: both passed; readiness returned `{"status":"ok"}`.
- `./scripts/smoke.sh`: expected exit 2 at the explicit missing-Celery gate; no placeholder jobs were added.
