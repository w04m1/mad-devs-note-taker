# Architecture

## System

The application uses React/TypeScript in the browser and FastAPI for HTTP and WebSockets. PostgreSQL is authoritative for notes, recurrence, reminder schedules, notifications, and transactional outbox events. Redis is a Celery broker and cross-process realtime transport. Celery Beat discovers due work; workers authorize and deliver reminders through an email adapter. Mailpit is the local SMTP implementation.

The deployment has seven long-lived services (`postgres`, `redis`, `mailpit`, `backend`, `worker`, `beat`, and `frontend`) plus a one-shot `migrate` service. Only `migrate` applies Alembic migrations.

## Transaction boundaries

- HTTP mutations own a database transaction.
- Entity changes, reminder reconciliation, parent version changes, and outbox records commit together.
- Redis and WebSocket messages are only invalidation hints. Clients refetch authoritative HTTP state.
- Celery tasks create their own synchronous database sessions.
- SQLAlchemy sessions are never shared between requests, tasks, or process forks.

## Concurrency and locks

Mutable aggregates have integer versions. Writes carry the expected version and return HTTP 409 on mismatch. Series mutations also check and increment the series version. The lock order is series, notes ordered by UUID, then reminder rules and deliveries ordered by UUID.

## Time

Persistent instants use UTC-backed `TIMESTAMPTZ`. API datetimes must include an offset. The profile IANA timezone controls display and grouping only. A recurrence series retains the timezone in which it was created. Monday starts the week. Reminder offsets are elapsed durations.

## Delivery boundary

A reminder delivery is unique by reminder-rule ID and cycle number. The worker commits `attempt_started`, the notification, content snapshot, and outbox event before exactly one application SMTP call. A crash after that boundary is retained as unknown and is never retried. This is at-most-one SMTP attempt, not exactly-once receipt.

See [`contracts.md`](contracts.md) for stable interface details and [`PLAN.md`](../PLAN.md) for the full rationale.
