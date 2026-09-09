# Backend development decision log

## 2026-04-01: application and dependency bootstrap

**Decision.** Use a Python 3.12 `uv` project with FastAPI, Pydantic Settings, SQLAlchemy 2,
Alembic, asyncpg for HTTP, and psycopg 3 for synchronous worker access. Commit `uv.lock`.

**Alternatives.** A single synchronous driver would simplify setup, but would block FastAPI request
workers. Running async SQLAlchemy inside Celery would add an event-loop lifecycle with no benefit.
Poetry and pip-tools were rejected because the repository plan specifies `uv` lockfiles.

**Evidence.** SQLAlchemy 2 documents separate async engines/session makers and states that sessions
must not be shared between concurrent tasks. FastAPI documents simple async health handlers. Current
compatible releases were resolved by `uv lock`, rather than copied from an unverified version list.

## 2026-04-01: health semantics

**Decision.** Liveness reports only process health. Readiness performs `SELECT 1` against PostgreSQL
and returns HTTP 503 when it cannot connect. This keeps orchestration from restarting a healthy API
process merely because its database is temporarily down.

**Alternatives.** Checking PostgreSQL in both probes couples liveness to an external service. Returning
200 with a degraded body from readiness prevents standard orchestrators from withdrawing traffic.

**Evidence.** The shared contract fixes both endpoint paths, and PostgreSQL is the authoritative store
in `PLAN.md`.
