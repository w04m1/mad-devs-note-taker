# Implementation status

Status is based on code present on this branch and the committed evidence in [verification](verification.md). `PLAN.md` remains the intended design and test plan; unchecked or described plan items are not implied to be complete.

## Implemented

- **Runtime:** Docker Compose defines PostgreSQL, Redis, Mailpit, FastAPI, Celery worker, Celery Beat, and Vite, plus a one-shot Alembic migration service.
- **Notes:** create, read, update, soft-delete, restore, active state, tags, reminder offsets, optimistic versions, server-side search/filter/sort/pagination, calendar reads, trash reads, and Upcoming groups.
- **Tags and settings:** tag create/rename/color/delete and singleton email/IANA timezone settings with version checks.
- **Recurrence:** finite daily/weekly/monthly materialization, occurrence edits, series split from a selected occurrence, series trash/restore, exception handling, and history protections.
- **Reminders:** PostgreSQL-backed delivery cycles, bounded due scans, Celery scheduling, eligibility recheck, in-app notification history, production SMTP delivery to Mailpit, outbox publishing, and the documented at-most-one application-attempt boundary.
- **Frontend:** notes, tags, settings, calendar month/week/day views and drag, Upcoming auto-boundary refresh, trash/restore, recurrence scope dialogs, conflict feedback, WebSocket-driven query invalidation, and live-toast deduplication.
- **Manual DST input:** an ambiguous fall-back wall time shows both valid offset-qualified occurrences and requires an explicit radio selection; neither is preselected. A selected offset-qualified instant is sent unchanged. DST gaps are rejected. Recurring schedules retain their separate contract of selecting the earlier instant.
- **Persistence and operations:** three Alembic revisions, named PostgreSQL/Redis volumes, health-gated startup, logical backup/restore scripts, volume-preserving shutdown documentation, and isolated automated restart/restore verification.

## Verified automated coverage

- The final main-branch `./scripts/test.sh` passed 18 safe backend tests with 27 deselected, 27 PostgreSQL/real-service tests with 18 deselected and zero skips, all migration cycles plus `alembic check`, 30 frontend tests across 12 files, and the production build.
- Six isolated Chromium Playwright scenarios pass across realtime/Upcoming, notification delivery and deduplication, calendar drag with different browser/profile zones, concurrent edit conflict, recurrence scopes, and trash/restore.
- Isolated real-service tests cover the production SMTP sender with Mailpit, Celery through Redis, multi-process WebSocket fanout through Redis Pub/Sub, PostgreSQL authorization races, lease recovery, and ambiguous `attempt_started` classification.
- The recovery gate verifies PostgreSQL and Redis persistence across restart and PostgreSQL logical backup/restore.
- The scale phase loads exactly 10,000 deterministic notes and records analyzed plans under its 500 ms regression ceiling. The final main-branch run measured calendar 0.087 ms, trigram search 17.06 ms, tag filter 6.473 ms, and trash 0.365 ms.

## Known deviations and limits

- **Frontend bundle:** The production build passes but emits a chunk warning. Recorded workstream builds place the main JavaScript chunk around 794–795 kB minified. Code splitting has not been done.
- **OpenAPI/TypeScript:** FastAPI publishes OpenAPI and focused tests pin selected response shapes. The frontend still uses handwritten contract-shaped DTOs. Generic `Page` does not encode a concrete item type, so this is partial contract protection, not complete OpenAPI client generation.
- **Email guarantee:** PostgreSQL and SMTP cannot guarantee exactly-once receipt. Ambiguous post-authorization outcomes are not retried. Automated coverage does not SIGKILL a worker at every instruction boundary or after Mailpit accepts `DATA`.
- **Realtime:** Redis Pub/Sub is non-replaying. Clients recover by refetching on reconnect/focus. Live multi-process fanout is verified, but Redis-outage behavior has not been black-box tested with a connection held open.
- **Concurrency and outage scope:** Authorization races cover a competing delivery and note deletion, not recurrence split or retention cleanup. Restart tests prove isolated persistence and restore, not full application availability during an outage.
- **Scale boundary:** The 10,000-note query-plan gate is a host-specific regression check, not a product latency SLO. It does not establish hardware percentiles or exactly-10,000 recurrence materialization latency.
- **E2E boundary:** Browser coverage is Chromium-only and serial. Its bounded delivery and deduplication windows do not model prolonged retries or broker outages.
- **Scope/security:** The app is intentionally unauthenticated and single-profile. It has no TLS and is not for public internet exposure.
