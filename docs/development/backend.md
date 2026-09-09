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

## 2026-04-01: relational schema and initial migration

**Decision.** Materialize every finite occurrence as a `notes` row and add every entity listed in
`PLAN.md`. UUIDs are generated in the application, instants use timezone-aware SQLAlchemy columns
(`TIMESTAMPTZ` on PostgreSQL), mutable aggregates use mapper version counters, and JSON payloads use
JSONB on PostgreSQL. Reminder offsets and delivery states exactly match `docs/contracts.md`.

**Alternatives.** Virtual recurrence expansion was rejected because it complicates complete search,
pagination, and durable scheduling. Database-generated UUIDs were rejected to avoid requiring another
extension. Native PostgreSQL arrays for offsets were rejected because rules and delivery cycles need
stable row identity.

**Evidence.** Metadata compilation tests verify the entities, constraints, timezone flags, and frozen
reminder contract without requiring PostgreSQL. The schema uses database uniqueness for recurrence
keys, reminder cycles, notifications, and associations, rather than relying only on service code.

## 2026-04-01: search and migration portability boundary

**Decision.** Store a generated lowercase title/body search expression and apply a PostgreSQL
`pg_trgm` GIN index. The initial Alembic migration enables `pg_trgm` and creates the reviewed metadata.
Application model types remain compilable for non-PostgreSQL unit tests, while production migrations
explicitly target PostgreSQL.

**Alternatives.** PostgreSQL full-text search adds stemming and language configuration that conflict
with predictable literal English/Russian substring matching. Plain `ILIKE` needs no extension but does
not meet the several-thousand-row responsive-search goal. A handwritten operation for every initial
column would duplicate the reviewed declarative metadata; later migrations will use Alembic
autogeneration and review.

**Evidence.** PostgreSQL documents `pg_trgm` support for indexed `LIKE`/`ILIKE` searches. `PLAN.md`
selects trigram substring matching and PostgreSQL as the authoritative store.

## 2026-04-01: demo email configuration validation

**Decision.** Store the configured default email as a string at settings-load time and validate it at
the API/domain boundary later. This preserves the frozen `demo@example.test` local default.

**Alternatives.** Pydantic `EmailStr` was tested, but its current validator rejects the reserved `.test`
domain even though that address is intentional for Mailpit. Changing the address would break the
environment contract. Disabling deliverability checks is not exposed by `EmailStr`.

**Evidence.** A settings construction test failed specifically because `example.test` is reserved; the
contract explicitly requires `demo@example.test`. SMTP configuration still controls actual delivery.
