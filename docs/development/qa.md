# QA decision and evidence log

## 2026-09-09 — Safe command boundaries

- **Decision:** `./scripts/test.sh` is the complete default gate. It builds backend and frontend images first, runs the non-PostgreSQL backend checks, invokes the mandatory PostgreSQL/service gate, then runs frontend tests and the production build. Building first is required because `docker compose run` otherwise can execute a stale local image. The marker split prevents destructive fixtures from running against the development database; it does not omit them from the overall command.
- **Decision:** `./scripts/test-postgres.sh` creates a unique Compose project with disposable PostgreSQL and Redis volumes plus an isolated Mailpit. It creates and migrates `notetaker_qa`, starts a dedicated Celery worker, runs marked integration tests, and removes the whole project through a trap.
- **Safety:** destructive fixtures only activate when `TEST_DATABASE_URL` is explicitly supplied and its database name contains `test` or `qa`. The mandatory gate sets `FAIL_ON_SKIP=1`; any selected test which skips makes the session fail instead of producing a misleading green result.
- **Alternative rejected:** silently setting `TEST_DATABASE_URL` to the development database or reusing the development Compose project. Either choice can destroy local rows, messages, or service state.

## 2026-09-09 — Immutable migration history

- **Decision:** Revision `0001` no longer imports current `Base.metadata`. It contains explicit table, constraint, enum, computed-column, and index operations. Its notes table intentionally excludes `superseded_at`, `series_trashed_at`, and `purged_at`; revisions 0002 and 0003 own those changes.
- **Gate:** the PostgreSQL command proves `base -> 0001`, asserts that later columns are absent, then proves `0001 -> head`, `alembic check`, `head -> 0001 -> head`, and `head -> base -> head` on a disposable database.
- **Tradeoff:** `CREATE EXTENSION IF NOT EXISTS pg_trgm` and downgrade's type cleanup remain SQL because these are PostgreSQL-specific facilities. Table history is no longer dynamic.

## 2026-09-09 — Real service and concurrency coverage

- **Redis/WebSocket:** a runtime test starts two independent uvicorn OS processes, connects one WebSocket to each, publishes one envelope through real Redis, and requires Redis to report two subscribers and both clients to receive the same event ID.
- **SMTP/Mailpit:** a claimed delivery goes through the production `SMTPEmailSender` to real Mailpit. Repeating the delivery task must produce one Mailpit message and one terminal `sent` row.
- **Celery:** a dedicated worker consumes from Redis database 15 while application pub/sub uses database 14. A task is sent through the actual broker and the test polls PostgreSQL for the worker's committed `published_at` result.
- **Authorization races:** two threads with independent SQLAlchemy sessions authorize the same claim concurrently; row locks must yield exactly one email payload and one notification. A second case races final authorization against note deletion in independent sync/async sessions. PostgreSQL lock order permits only two valid outcomes: deletion wins with a cancelled delivery and no notification, or authorization wins with one `attempt_started` delivery and one notification.
- **Crash boundary already covered:** the existing PostgreSQL suite proves expired lease recovery and classification of a committed `attempt_started` record as `unknown`. The real runtime suite does not SIGKILL a worker at each instruction boundary; deterministic failpoint hooks would be required to avoid timing-based false evidence.
- **Deviation:** Redis outage WebSocket `resync_required` is not yet black-box tested during an open connection. The subscriber implementation is covered only by unit behavior plus live fanout. Authorization is not yet raced against recurrence split or retention cleanup; those paths use the documented series/note lock order, but the current black-box race evidence covers deletion only. Service-wide restart is isolated in the recovery gate below.

## 2026-09-09 — Restart, persistence, backup and restore

- **Decision:** `./scripts/test-recovery.sh` creates a unique disposable Compose project. It uses only `notetaker_qa_recovery`, writes PostgreSQL and Redis sentinels, restarts both services without deleting volumes, and verifies both sentinels. It then performs a logical `pg_dump`, replaces only the QA database, restores it with `ON_ERROR_STOP`, and verifies the row count.
- **Safety/deviation:** the trap removes the dedicated project and volumes, so the command does not restart shared development services. It does not claim full application availability during outage or a worker kill after Mailpit accepts DATA.

## 2026-09-09 — Deterministic 10k data and query plans

- **Decision:** `backend/scripts/qa_dataset.py` resets the isolated database and inserts exactly 10,000 notes and deterministic tag associations with PostgreSQL `generate_series` and stable MD5-derived UUIDs. Fixed timestamps and distribution make runs comparable.
- **Evidence format:** it emits `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` for calendar, trigram search, tag filter, and trash queries. It records PostgreSQL execution time and client wall time.
- **Limit:** the default 500 ms ceiling is a regression tripwire, not a product latency SLO. Hardware-sensitive percentiles and exactly-10,000 recurrence materialization are not claimed. The tool reports plans so reviewers can distinguish planner changes from host load.
- **Artifact decision:** the gate writes through a temporary bind-mounted directory, then copies full JSON to `QA_PLAN_OUTPUT` (default `/tmp/notetaker-qa-query-plans.json`). Direct file mounts were rejected because Docker denied replacement of the mounted inode in the audited environment even at mode `0666`.

## Commands

```sh
./scripts/test.sh                 # complete backend/service/frontend gate
./scripts/test-postgres.sh        # focused isolated PostgreSQL + real services + plans
./scripts/test-recovery.sh        # explicit service restart and backup/restore gate
```

## Manual full-stack evidence supplied by integration owner

- After a fresh migration, note `ce69ad83` was created through the frontend proxy with `starts_at` about 10 minutes ahead and a 10-minute reminder.
- The real worker authorized it about one second late. Mailpit recorded exactly one message to `demo@example.test`, with Message-ID ending `24325b70...1@notetaker.local`. `GET /notifications` returned one matching persisted item.
- The automated Mailpit case uses the same production `deliver` and `SMTPEmailSender` boundary. It uses a fixed isolated test database and asserts a repeated task call still leaves one message.

## Current verification record

- `uv run --frozen ruff check .`: passed.
- Direct safe backend selection: 17 passed, 17 deselected; two upstream Starlette/httpx deprecation warnings.
- `./scripts/test.sh` before making PostgreSQL mandatory within it: backend 18 passed/19 skipped, frontend 28 passed across 12 files, and production build passed. Vite warned that the main 793.95 kB minified chunk exceeds 500 kB.
- Initial real-service gate: 16 passed/17 deselected in 10.58 s. The full migration cycle and `alembic check` passed. Query execution times were calendar 0.082 ms, search 6.312 ms, tag filter 1.476 ms, and trash 0.207 ms.
- Initial recovery gate passed PostgreSQL and Redis restart persistence plus PostgreSQL logical restore.
- Audit failure retained: the first two isolated artifact attempts completed all 16 tests but failed copying query-plan evidence due to direct bind-file `PermissionError`. The final temporary-directory design passed; its pre-race run recorded 16 passed/17 deselected in 11.99 s and retained 15,272 bytes of JSON with execution times 0.096, 9.381, 1.786, and 0.356 ms respectively.
- Final isolated service verification after the delete-race and fail-on-skip additions: 17 passed/17 deselected, zero skips, in 27.88 s. The full migration cycle and `alembic check` passed. The retained 15,275-byte JSON recorded calendar 0.087 ms, search 10.360 ms, tag filter 1.918 ms, and trash 0.280 ms.
- Final isolated recovery verification passed PostgreSQL and Redis restart persistence plus PostgreSQL logical restore. Its trap removed the dedicated project and volumes.
- Audit finding: the first complete default-gate run used a pre-existing backend image for its initial phase (18 passed/19 skipped), although its nested service gate rebuilt the image and passed 17 tests with zero skips. The command now builds both images before any tests. Final post-fix `./scripts/test.sh`: non-service backend 17 passed/17 deselected in 3.74 s; isolated service backend 17 passed/17 deselected with zero skips in 15.10 s; frontend 25 passed across 11 files; production build passed in 662 ms. Query times were calendar 0.069 ms, search 14.852 ms, tag filter 2.393 ms, and trash 0.336 ms. The two known upstream Starlette/httpx warnings and the Vite 793.95 kB chunk-size warning remain.

The dates in this log follow the repository integration date (2026-09-09). The measured values are evidence for this host and run, not latency promises.
