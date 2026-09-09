# Implementation status

Status is based on code present on this branch and the evidence in [verification](verification.md). `PLAN.md` remains the intended design and test plan; unchecked or described plan items are not implied to be complete.

## Implemented

- **Runtime:** Docker Compose defines PostgreSQL, Redis, Mailpit, FastAPI, Celery worker, Celery Beat, and Vite, plus a one-shot Alembic migration service.
- **Notes:** create, read, update, soft-delete, restore, active state, tags, reminder offsets, optimistic versions, server-side search/filter/sort/pagination, calendar reads, trash reads, and Upcoming groups.
- **Tags and settings:** tag create/rename/color/delete and singleton email/IANA timezone settings with version checks.
- **Recurrence:** finite daily/weekly/monthly materialization, occurrence edits, series split from a selected occurrence, series trash/restore, exception handling, and history protections.
- **Reminders:** PostgreSQL-backed delivery cycles, bounded due scans, Celery scheduling, eligibility recheck, in-app notification history, Mailpit SMTP adapter, outbox publishing, and the documented at-most-one application-attempt boundary.
- **Frontend:** notes, tags, settings, calendar month/week/day views and drag, Upcoming auto-boundary refresh, trash/restore, recurrence scope dialogs, conflict feedback, WebSocket-driven query invalidation, and live-toast deduplication.
- **Persistence and operations:** three Alembic revisions, named PostgreSQL/Redis volumes, health-gated startup, logical backup/restore scripts, and volume-preserving shutdown documentation.

## Known deviations and limits

- **DST overlap input:** Manual note entry shows both valid offset-qualified occurrences for an ambiguous fall-back wall time and requires an explicit radio selection. DST gaps are rejected. Recurring schedules continue to select the earlier instant by contract.
- **Frontend bundle:** The current production build passes but emits a chunk warning. The main JavaScript chunk is 795.00 kB minified (240.68 kB gzip). Code splitting has not been done.
- **OpenAPI/TypeScript:** FastAPI publishes OpenAPI and focused tests pin selected response shapes. The frontend still uses handwritten contract-shaped DTOs. Generic `Page` does not encode a concrete item type, so this is partial contract protection, not complete OpenAPI client generation.
- **Email guarantee:** A real reminder reached Mailpit in one manual integrated check. Automated real-SMTP regression is pending. PostgreSQL and SMTP cannot guarantee exactly-once receipt; ambiguous post-authorization outcomes are not retried.
- **Realtime:** Redis Pub/Sub is non-replaying. Clients recover by refetching on reconnect/focus. Multi-process fanout and Redis outage recovery still need final QA evidence.
- **Scope/security:** The app is intentionally unauthenticated and single-profile. It has no TLS and is not for public internet exposure.
- **Scale and resilience:** The planned several-thousand-note performance run, restart/failure matrix, crash injection, and high-contention tests do not yet have final results on this branch.

## Pending integration evidence

The six planned Playwright scenarios and final QA work are active outside this branch. Their pass/fail results are not recorded as complete here. Only reviewed results merged into this branch should update [verification](verification.md).
