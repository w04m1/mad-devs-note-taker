# Implementation status

The functional audit of application baseline `defa868` is frozen with 15 unresolved release blockers. No remediation has begun, and the audited implementation is not release-ready. The [functional audit ledger](development/functional-audit.md) is authoritative for current findings and contracts; [verification](verification.md) keeps evidence scoped to what each check exercised. `PLAN.md` remains a design and test plan, not completion evidence.

## Present implementation surface

This is an inventory, not a completeness or readiness claim.

- **Runtime:** Docker Compose defines PostgreSQL, Redis, Mailpit, FastAPI, Celery worker, Celery Beat, and Vite, plus a one-shot Alembic migration service.
- **Notes:** create, read, update, soft-delete, restore, active state, tags, reminder offsets, optimistic versions, server-side search/filter/sort/pagination, calendar reads, trash reads, and Upcoming groups.
- **Tags and settings:** tag create/rename/color/delete and singleton email/IANA timezone settings with version checks.
- **Recurrence:** finite daily/weekly/monthly materialization, occurrence edits, series split from a selected occurrence, series trash/restore, exception handling, history protections, and a linear open-tip-only successor invariant.
- **Reminders:** PostgreSQL-backed delivery cycles, bounded due scans, Celery scheduling, eligibility recheck, in-app notification history, production SMTP delivery to Mailpit, outbox publishing, and the documented at-most-one application-attempt boundary.
- **Frontend:** notes, tags, settings, calendar month/week/day views and drag, Upcoming auto-boundary refresh, trash/restore, recurrence scope dialogs, conflict feedback, WebSocket-driven query invalidation, and live-toast deduplication.
- **Manual DST input:** an ambiguous fall-back wall time shows both valid offset-qualified occurrences and requires an explicit radio selection; neither is preselected. A selected offset-qualified instant is sent unchanged. DST gaps are rejected. Recurring schedules retain their separate contract of selecting the earlier instant.
- **Persistence and operations:** three Alembic revisions, named PostgreSQL/Redis volumes, health-gated startup, logical backup/restore scripts that are present but not failure-safe or atomic, volume-preserving shutdown documentation, and isolated automated restart/restore verification.

## Historical pre-audit automated evidence

- The historical main-branch `./scripts/test.sh` passed 18 safe backend tests with 27 deselected, 27 PostgreSQL/real-service tests with 18 deselected and zero skips, all migration cycles plus `alembic check`, 30 frontend tests across 12 files, and the production build.
- Six isolated Chromium Playwright scenarios passed across realtime/Upcoming, notification delivery and deduplication, calendar drag with different browser/profile zones, concurrent edit conflict, recurrence scopes, and trash/restore.
- Isolated real-service tests covered the production SMTP sender with Mailpit, Celery through Redis, multi-process WebSocket fanout through Redis Pub/Sub, PostgreSQL authorization races, lease recovery, and ambiguous `attempt_started` classification.
- The recovery gate verified PostgreSQL and Redis persistence across restart and PostgreSQL logical backup/restore.
- The scale phase loaded exactly 10,000 deterministic notes and records analyzed plans under its 500 ms regression ceiling. That historical main-branch run measured calendar 0.087 ms, trigram search 17.06 ms, tag filter 6.473 ms, and trash 0.365 ms.

## Fresh functional-audit evidence

- On exact baseline `defa868`, `./scripts/test.sh` passed 18 safe backend tests, 28 isolated PostgreSQL/real-service tests, 30 frontend tests in 12 files, and the production build. The build emitted a 795.00 kB main chunk (240.68 kB gzip) and the expected size warning.
- A fresh isolated E2E run passed all 6 Chromium scenarios in 36.3 seconds; the complete wrapper took 81.6 seconds.
- Exactly-10,000-occurrence materialization had a 15.740-second warm median with no offsets and a 99.940-second warm median with all three offsets; the latter ranged from 89.061 to 105.497 seconds. Visibility was atomic and concurrent reads stayed responsive. This remains a blocker because no owner-approved performance exception exists.
- Exact commands, artifacts, reproductions, and boundaries are in the [functional audit ledger](development/functional-audit.md).

## Unresolved release blockers

The 15 blockers are grouped here only for navigation; the [ledger](development/functional-audit.md#frozen-release-blocker-map) owns IDs and acceptance contracts.

- Recovery, backup integrity and targeting, and schema activation.
- Durable grouped recurring Trash, purge redaction, and superseded-note direct-ID/reminder access.
- Reminder and cleanup backlogs, plus recipient authorization.
- Stale future-split intent in Note and Calendar flows.
- Upcoming shared pagination.
- Authoring timezone races.
- Beat progress health.
- Maximum-size recurrence materialization.

No remediation or post-remediation rerun exists.

## Accepted product and test limits

- SMTP provides at most one application attempt, not exactly-once external receipt.
- Recurrence retains its finite 10,000 cap, skipped invalid candidates, and earlier-fold rule; list and Calendar caps remain documented.
- Redis Pub/Sub is non-replaying. HTTP is authoritative, with refetch-based recovery.
- The product is local, unauthenticated, single-profile, and has no TLS. It is not for public internet exposure.
- Browser E2E is Chromium-only and serial. Performance evidence is host-sensitive. Third-party logs remain native.
- Purge may retain minimal non-public technical tombstones, but not user-authored content or public API visibility.

## Other unresolved findings

Bundle size, OpenAPI/client generation, accessibility, structured logging, and the other nonblocking findings and evidence gaps remain recorded in the [functional audit ledger](development/functional-audit.md). They are not duplicated here.
