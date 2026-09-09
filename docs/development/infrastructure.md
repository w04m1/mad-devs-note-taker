# Infrastructure decision log

## 2026-09-09T18:12:00Z — Compose topology and pinned runtimes

- **Problem or decision:** Provide the requested process topology without hiding extra daemons in application containers.
- **Chosen approach and reason:** Define exactly seven long-lived services (`postgres`, `redis`, `mailpit`, `backend`, `worker`, `beat`, `frontend`) and one one-shot `migrate`. Use exact version tags for PostgreSQL 16.4, Redis 7.4.1, Mailpit 1.21.7, Python 3.12.7, uv 0.5.11, Node 22.11.0, and pnpm 9.12.3 so upgrades are reviewed rather than floating through `latest`.
- **Alternative and tradeoff:** Combining worker and Beat or running migrations in every backend replica would use fewer containers, but creates duplicate schedulers and migration races. Immutable registry digests would resist tag replacement more strongly, but are architecture-specific and harder to maintain for this multi-platform local stack; exact release tags are the chosen pinning level.
- **Evidence:** `docker compose config --quiet` succeeds and reports eight service definitions.
- **Deviations or unresolved work:** Image builds require the backend/frontend locked manifests from parallel workstreams.

## 2026-09-09T18:12:10Z — Startup and health gates

- **Problem or decision:** Avoid application boot against an unavailable database, unapplied schema, broker, or SMTP emulator.
- **Chosen approach and reason:** Use native PostgreSQL, Redis, and Mailpit probes; gate the migration on PostgreSQL health; gate application processes on successful migration and required dependencies; gate frontend on backend readiness. Worker health uses a Celery addressed ping. Beat has a single-instance PID/process probe.
- **Alternative and tradeoff:** Port-open checks are simpler but accept services before they can do useful work. A separate Beat heartbeat persisted in PostgreSQL would prove actual scheduling progress better than a PID, but needs application-owned task code not present in this infrastructure wave.
- **Evidence:** Compose normalization retains `service_healthy` and `service_completed_successfully` conditions. Health commands use tools already present in their images or small stdlib probes.
- **Deviations or unresolved work:** The backend workstream must implement the readiness semantics. Replace or augment the Beat PID probe when a scheduler-heartbeat API/table exists.

## 2026-09-09T18:12:20Z — Persistence and host exposure

- **Problem or decision:** Preserve authoritative state and improve broker recovery without casually exposing an unauthenticated application.
- **Chosen approach and reason:** Put PostgreSQL and Redis in named volumes. Enable Redis AOF with one-second fsync. Publish only frontend and Mailpit UI on loopback, leaving PostgreSQL, Redis, SMTP, and backend internal.
- **Alternative and tradeoff:** Redis snapshots write less frequently, but lose a wider window. Publishing all ports simplifies host debugging but expands attack surface. Persisting Mailpit would retain developer mail, but messages are test evidence rather than application state.
- **Evidence:** Rendered Compose has only ports 5173 and 8025 and declares `postgres_data` and `redis_data`.
- **Deviations or unresolved work:** AOF still can lose about one second. PostgreSQL remains authoritative and must recover broker/outbox work.

## 2026-09-09T18:12:30Z — Shared, layout-tolerant application images

- **Problem or decision:** Infrastructure and application branches are parallel, while backend, migration, worker, and Beat must use identical code and dependencies.
- **Chosen approach and reason:** Build one backend image and reuse it through a YAML anchor. Dockerfiles copy each complete project context and install from frozen lockfiles, which tolerates normal additions below `app/`, `migrations/`, `src/`, and generated directories. Commands follow the frozen module contract.
- **Alternative and tradeoff:** Copying manifest files before source gives better rebuild caching, but Docker fails at parse/build time when the parallel branch files are temporarily absent and it encodes more layout assumptions. Conditional unlocked installs would build earlier but destroy reproducibility.
- **Evidence:** Dockerfiles use `uv sync --frozen` and `pnpm install --frozen-lockfile`; operations docs list the module and script contract.
- **Deviations or unresolved work:** Full image builds cannot be validated until `pyproject.toml`, `uv.lock`, `package.json`, and `pnpm-lock.yaml` are integrated.

## 2026-09-09T18:12:40Z — Same-origin Vite development routing

- **Problem or decision:** Browsers cannot resolve Compose DNS names and HTTP/WebSocket calls should share one visible origin.
- **Chosen approach and reason:** Browser clients use relative `/api` and `/ws`; the Vite server receives `VITE_PROXY_TARGET=http://backend:8000` and must proxy both, including WebSocket upgrade. Only Vite is published as the app endpoint.
- **Alternative and tradeoff:** Publishing backend and putting an absolute API URL into the frontend is easy, but creates CORS and physical-device configuration drift. A reverse-proxy service would be production-like but would violate the exact seven-service topology.
- **Evidence:** Compose exports the target only to frontend and the smoke probe reaches readiness through port 5173.
- **Deviations or unresolved work:** The frontend workstream must implement the two Vite proxy entries.

## 2026-09-09T18:12:50Z — Operator scripts and destructive boundaries

- **Problem or decision:** Startup alone does not provide reproducible evidence or safe day-to-day operations.
- **Chosen approach and reason:** Add scripts for Compose validation, full-stack smoke checks, locked backend/frontend tests, and confirmed logical backup/restore. Document that normal `down` preserves volumes and `down --volumes` destroys them. On smoke failure, retain containers and print logs for diagnosis.
- **Alternative and tradeoff:** Automatically tear down after every smoke run gives cleaner hosts but erases the most useful failure state. Raw volume copying is fast but is unsafe without filesystem/database coordination; `pg_dump` is portable and online-safe.
- **Evidence:** Shell syntax checks and Compose validation are part of this wave's checks; scripts use `set -eu` and fail-fast HTTP probes.
- **Deviations or unresolved work:** Cross-service application and E2E tests await integrated feature code.

## 2026-09-09T18:13:00Z — LAN override and security limit

- **Problem or decision:** Two-device testing needs a non-loopback listener, while the product intentionally has no login.
- **Chosen approach and reason:** Keep secure loopback defaults and document an explicit `0.0.0.0` frontend override plus exact allowed origin for a trusted LAN.
- **Alternative and tradeoff:** Binding to all interfaces by default reduces setup for physical clients but risks unintended access. Adding TLS/auth belongs to a different product scope.
- **Evidence:** `.env.example` defaults both published services to `127.0.0.1`; operations docs include the opt-in override and warning.
- **Deviations or unresolved work:** No production exposure is supported.
