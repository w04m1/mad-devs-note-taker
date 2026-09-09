# Background reminders, email, and realtime decision log

## 2026-09-09 — Dependency and process boundary

**Decision.** Add locked Celery 5, Redis 5, and python-dateutil 2 dependencies. The existing shared image now provides `app.jobs.celery_app:celery_app` to the Compose worker and single Beat process. Beat uses the configured one-second reminder/outbox intervals, a fixed 60-second maintenance interval, and the configured hourly trash interval. All task payloads are JSON and workers use a fresh synchronous SQLAlchemy session for each transaction.

**Alternative.** Long-lived Celery ETA tasks were rejected. PostgreSQL must remain authoritative and Redis loss must not erase a deadline. Async worker sessions were rejected because the existing architecture explicitly separates async HTTP sessions from sync task sessions.

**Evidence.** `test_beat_schedule_and_registered_tasks` checks task registration and schedule names. Compose already had one Beat instance; the worker now also waits for healthy Mailpit because it can call SMTP immediately.

## 2026-09-09 — Claiming, grace, and recovery

**Decision.** Each scan locks at most 100 due `pending` or lease-expired `claimed` rows using `FOR UPDATE SKIP LOCKED`. It marks deadlines older than the configured grace as `missed`; otherwise it writes a new UUID token and configured lease, commits, and only then enqueues `(delivery_id, token)`. Enqueue failure leaves a recoverable lease rather than undoing the durable claim.

**Alternative.** Publishing jobs before the database commit risks a worker observing uncommitted state. Keeping a database transaction open while sending to Celery couples availability and was rejected. Claims do not lock note aggregates: discovery only owns delivery scheduling state; final authorization performs the aggregate lock protocol.

**Evidence.** The query is bounded and ordered by due time/UUID. Terminal authorization outcomes clear stale claim metadata. Duplicate and stale jobs are rejected by the token/state checks at authorization. The downtime policy remains skip after 60 seconds by default; no notification or SMTP attempt is made for `missed` work.

## 2026-09-09 — Final authorization and SMTP crash boundary

**Decision.** The worker first discovers foreign keys without locks, then locks series (when present), note, reminder rule, and delivery in that order. It rechecks token, current cycle, enabled/active/deleted status, due time, and grace. The winning transaction commits `attempt_started`, recipient/content snapshots, one unique Notification, and its outbox event. Only after commit does it call the injected `EmailSender` once. A second transaction records `sent` or `failed`. Maintenance changes old `attempt_started` rows to `unknown` and never retries SMTP.

**Alternative.** SMTP before authorization can send after a concurrent delete. Retrying `attempt_started` may duplicate accepted email after an ambiguous SMTP timeout. Exactly-once receipt cannot be achieved across PostgreSQL and SMTP without receiver support, so both alternatives were rejected.

**Evidence.** The stable `Message-ID` derives from delivery UUID and cycle. The fake sender records attempts deterministically. SMTP adapter tests cover envelope headers, STARTTLS, authentication, and timeout wiring. A crash after authorization but before SMTP can lose an email; a crash after SMTP but before result commit is ambiguous. Both are intentionally classified `unknown`, preserving the agreed at-most-one application attempt. SMTP timeout and server-disconnect exceptions are also treated as ambiguous and recorded as `unknown`; definitive failures are `failed`. Missing or malformed recipients skip SMTP. Failure and unknown outcomes update the persistent notification title and enqueue another stable-ID invalidation event, so the error is visible without suppressing the in-app notification.

## 2026-09-09 — Transactional outbox publication

**Decision.** The publisher locks up to 100 committed, due, unpublished events with `SKIP LOCKED`, publishes the stored payload unchanged to `notetaker.events`, and marks `published_at` only on success. Failures record a bounded error, attempt count, and exponential retry delay capped at 60 seconds.

**Alternative.** A Redis stream or new outbox lease columns would avoid holding locks during publish but adds schema/state that is not needed at this local scale. This implementation keeps the transaction open for a bounded Redis call. A crash after Redis accepted an event and before commit can duplicate it; the stable event ID makes that safe for consumers.

**Evidence.** HTTP mutations already create outbox rows in their database transactions. The publisher never manufactures a replacement event ID.

## 2026-09-09 — Local WebSocket fanout and recovery

**Decision.** `/ws` registers sockets in a process-local connection manager. A FastAPI lifespan task subscribes to Redis asynchronously and forwards validated event envelopes to every local socket. Redis connection failure does not stop HTTP. The subscriber reconnects with bounded exponential delay and emits `resync_required` both when degradation is first detected and after recovery. This lets connected clients begin their 30-second fallback reconciliation instead of remaining silently stale. Broken sockets are removed during fanout.

**Alternative.** Direct worker-to-WebSocket delivery fails with multiple API processes. Redis Pub/Sub was retained instead of a replay log because messages are only invalidation hints and HTTP is authoritative.

**Evidence.** The fanout test covers multiple sockets, broken-socket removal, and recovery-envelope delivery. Redis payloads missing event ID/type or invalid JSON are ignored.

## 2026-09-09 — Retention cleanup

**Decision.** Cleanup finds at most 100 notes deleted for 30 days, locks related series in UUID order and then notes in UUID order, redacts note text, notification text, exception override content, and delivery recipient/content snapshots; removes tag associations; sets `purged_at`; and emits `note.deleted` invalidations. Already-purged rows are excluded, which makes repeated cleanup idempotent. A new `0002` migration adds the purge marker and index. It checks the live schema because the inherited `0001` migration builds from mutable ORM metadata: a fresh database already sees the new column while an older database does not. This compatibility guard avoids duplicate-column failure without rewriting released migration history. Public note lookup and Trash exclude purged technical records. Maintenance also deletes notification history and successfully published outbox events older than 30 days.

**Alternative.** Hard-deleting notes would cascade or orphan reminder audit identities and would remove recurrence records needed to prevent regeneration. Leaving redacted rows visible in Trash would not meet automatic permanent removal from the user-visible product. The purge marker preserves both requirements.

**Evidence.** Cleanup rechecks the retention predicate while holding note locks, so restore and purge serialize. Lock order remains series, ordered notes, then reminder/delivery rows; the snapshot update does not lock those rows before notes.

## Verification status and deviations

- Unit suite and Ruff are run from `backend` with `uv run --frozen`.
- `backend/tests/conftest.py` maps an explicitly supplied `TEST_DATABASE_URL` to the application `DATABASE_URL` before engines are imported. This prevents destructive integration fixtures from using an unrelated developer database.
- Real PostgreSQL/Redis/Mailpit integration is attempted through Compose when the runtime is available. Tests that need PostgreSQL remain explicitly skipped unless `TEST_DATABASE_URL` is set; skipped tests are reported rather than presented as passing integration evidence.
- python-dateutil is locked now because it is part of the agreed backend wave and recurrence runtime, although reminder job code itself uses elapsed `timedelta` offsets.


## 2026-09-09 — Final audit and verification

**Decision.** Treat malformed recipients as definitive failures without calling SMTP. Treat `TimeoutError`, socket timeout, and `SMTPServerDisconnected` as ambiguous because they can occur after DATA acceptance. Both paths keep the already-created in-app notification and make the outcome visible by updating its title; a second `notification.created` invalidation uses the same `notification_id`, so live-tab toast deduplication prevents a duplicate toast while HTTP history refreshes.

**Audit fixes.** Cleanup now excludes its own purge markers and removes content from notifications and occurrence overrides as well as notes and delivery snapshots. Redis subscriber failure signals degradation immediately and again on recovery. PostgreSQL tests route the explicit test URL before application engines are constructed. Terminal cancelled/missed deliveries clear stale claim metadata.

**Evidence.** `uv run --frozen ruff format --check .`, `ruff check .`, and the local pytest run pass (10 tests pass, 9 PostgreSQL tests skip without an explicit database). A Compose-backed PostgreSQL run passes all 19 tests. A separate fresh Compose project applies `0001` then `0002`, and a `0002 -> 0001 -> 0002` downgrade/upgrade cycle succeeds. `docker compose config -q` succeeds. Backend, worker, Beat, PostgreSQL, Redis, and Mailpit start successfully; Beat dispatches scans/publishing and the worker consumes them.

**Limits.** Automated tests drive the transaction helpers and task entry point against real PostgreSQL, but do not automate a real SMTP exchange, Redis outage, multi-process WebSocket fanout, crash injection, or high-contention lock races. The live Compose smoke check establishes process wiring only. Redis Pub/Sub remains non-replaying; clients must refetch on degradation/recovery/focus as documented. SMTP/PostgreSQL cannot provide exactly-once receipt.
