# Verification record

This page separates checks run on the original documentation baseline from later committed automated evidence. A command passing proves only what that command exercises.

**Current status:** Task 1 remediation is complete and all 15 frozen release
blockers have post-remediation evidence. The baseline findings remain preserved
in the [functional audit ledger](development/functional-audit.md).

## Post-remediation release verification (2026-09-10)

| Check | Result | Boundary |
|---|---|---|
| `cd backend && uv run --frozen ruff check .` | Pass | Current backend source and tests. |
| Safe backend pytest selection | 19 passed | Tests that do not require PostgreSQL, Redis, Celery, or Mailpit. |
| `QA_COMPOSE_PROJECT_NAME=<isolated> ./scripts/test-postgres.sh` | 34 passed, 19 deselected | Fresh PostgreSQL schema cycles, irreversible cutover, legacy ghost repair, immutable Trash storage, API races, real Redis/Celery/Mailpit, and query-plan capture. No skips. |
| `cd frontend && corepack pnpm test -- --run` | 38 passed in 14 files | Includes shared Upcoming paging, timezone pinning, exact-instant preservation, stable future-split intent, and Calendar stale-intent rejection. |
| `cd frontend && corepack pnpm build` | Pass; 3,059 modules transformed | Production TypeScript/Vite build. The existing bundle-size warning remains nonblocking. |
| `QA_COMPOSE_PROJECT_NAME=<isolated> ./scripts/test-recovery.sh` | Pass | Failure-injected dump/compression/write, corrupt and mid-SQL restore, target mismatch, valid atomic restore, exact schema gating, Beat suspension, and Redis loss. |
| `QA_MATERIALIZATION_COMPOSE_PROJECT_NAME=<isolated> ./scripts/test-materialization.sh` | Pass | Three runs per case; exact counts, zero rollback residue, atomic visibility, responsive concurrent reads, and retained JSON evidence. |

The performance owner gate is a median at or below 10 seconds for 10,000
occurrences without offsets, at or below 45 seconds with all three offsets, and a
maximum concurrent read below 2 seconds. The retained run measured 1.446 and
9.674-second medians respectively, with a 1.136-second worst read. Every run
materialized exactly 10,000 notes; the three-offset runs also materialized 30,000
rules and 30,000 deliveries. The artifact is
[`development/evidence/task1-materialization.json`](development/evidence/task1-materialization.json).

## Original baseline checks (2026-09-09)

Run from repository revision `26257ff` before the documentation commits:

| Check | Result | Boundary |
|---|---|---|
| `./scripts/compose-config.sh` | Pass | Compose parses and normalizes. |
| `cd backend && uv run --frozen ruff check .` | Pass | Ruff checks the baseline backend tree. |
| `cd backend && uv run --frozen pytest` | 18 passed, 19 skipped, 2 dependency deprecation warnings | The skipped tests require `TEST_DATABASE_URL`; this run is not PostgreSQL integration evidence. |
| `cd frontend && corepack pnpm test` | 28 passed in 12 files | Component/unit tests only; this command is not browser E2E. |
| `cd frontend && corepack pnpm build` | Pass; 2,086 modules transformed | Main JS chunk was 793.95 kB minified (240.31 kB gzip), above Vite's 500 kB warning threshold. |
| `./scripts/smoke.sh` | Pass | Built and started the stack, completed migration, found exactly seven running services, and reached the frontend, proxied readiness endpoint, and Mailpit API. It did not create product data or send email. |

The backend test run used Python 3.12.10. The frontend run used pnpm 11.21.0 and Vite 8.2.2.

## Historical committed automated evidence (pre-functional-audit)

The workstream command details and measured results are in the [QA log](development/qa.md) and [E2E log](development/e2e.md). The later final main-branch reconciliation is recorded in the [documentation decision log](development/documentation.md).

- The “final main-branch” historical workstream label below is not an audit-closure or release-readiness claim. That `./scripts/test.sh` run passed 18 safe backend tests with 27 deselected, then 27 isolated PostgreSQL/real-service tests with 18 deselected and zero skips. Its service phase passed the `0001` → head, head → `0001` → head, head → base → head migration cycles and `alembic check`. The frontend phase passed 30 tests across 12 files and the production build. Both images were built before tests, so the command did not reuse a stale application image.
- The real-service gate exercised the production SMTP sender against Mailpit and proved that a repeated delivery task leaves one message and one terminal `sent` row. It also exercised a real Celery worker through Redis and two uvicorn processes receiving one event through real Redis Pub/Sub.
- PostgreSQL concurrency tests proved single-winner authorization and the two permitted authorization-versus-delete outcomes. Deterministic tests also cover expired-lease recovery and classification of committed `attempt_started` work as `unknown`.
- `./scripts/test-recovery.sh` passed isolated PostgreSQL and Redis restart persistence and PostgreSQL logical dump, database replacement, restore, and row verification.
- The deterministic scale phase loaded exactly 10,000 notes and emitted retained JSON `EXPLAIN (ANALYZE, BUFFERS)` plans. The final main-branch `./scripts/test.sh` recorded calendar 0.087 ms, trigram search 17.06 ms, tag filter 6.473 ms, and trash 0.365 ms; all were below the gate's 500 ms regression ceiling.
- The isolated Playwright audit installed from its frozen lockfile, passed `tsc --noEmit`, and passed all six Chromium scenarios in 40.7 seconds. It covers cross-context realtime and Upcoming transitions, notification delivery/deduplication through Mailpit and Redis, timezone-sensitive calendar drag, stale-edit conflict handling, recurrence edit/delete/split, and cross-context trash/restore.

After the final correctness integration, the root reran `./scripts/test-recovery.sh` successfully and reran all six Playwright scenarios on a fresh isolated stack: 6 passed in 37.4 seconds. After the final lineage fix, the focused isolated PostgreSQL/service gate passed 28 selected tests with zero skips and the recurrence Playwright scenario passed again in 4.2 seconds. `./scripts/smoke.sh` then passed with seven healthy long-lived services and a completed migration.

## Manual integrated evidence

The integration log records a fresh-volume stack run with migrations through `0003_background`, seven healthy long-lived services, proxied readiness returning `{"status":"ok"}`, and an addressed worker `pong`.

A separate manual integrated check created note `ce69ad83-9f4c-4b47-b4d2-58f184cebf09` through the frontend proxy. Beat and the worker processed its due reminder. Mailpit contained exactly one message to `demo@example.test`, with stable `Message-ID` `24325b70-0336-4c8b-af5a-f414704229f9.1@notetaker.local`. Persistent notification `7d0d7910-745e-4a22-b441-18bb3fcda6cf` matched that delivery. The source record is [`docs/development/integration.md`](development/integration.md). This manual result supplements rather than substitutes for the automated SMTP evidence above.

## Functional-audit evidence (2026-09-10)

The [functional audit ledger](development/functional-audit.md) records exact commands, artifacts, and boundaries.

| Check or reproduction | Fresh result and boundary |
|---|---|
| Exact-baseline `./scripts/test.sh` | 18 safe backend and 28 isolated PostgreSQL/real-service tests passed; 30 frontend tests in 12 files and the build passed. The main chunk was 795.00 kB (240.68 kB gzip), with the expected warning. |
| Selected real-service gate | 9 PostgreSQL/Redis/Celery/Mailpit tests passed in a fresh isolated project. |
| Fresh isolated E2E | 6 Chromium scenarios passed in 36.3 seconds; the complete wrapper took 81.6 seconds. |
| Exactly-10,000 materialization | Warm median was 15.740 seconds without offsets and 99.940 seconds with all three offsets (89.061–105.497-second range). Writes were atomic and concurrent reads stayed responsive; performance is blocking without an owner exception. |
| Realtime outage | An existing socket signaled degradation but stayed open; a late socket lacked the initial signal; readiness stayed 200; a durable mutation was unseen for 32.012 seconds before recovery resync. |
| Backup/restore negative pipelines | Shell reproductions showed upstream dump/decompression failures can be masked by the last successful pipeline member. |
| Deployment-negative checks | Initial failed migration blocked dependents, but later direct restarts bypassed migration gating and frontend health masked a proxied API failure. |
| Beat wedge | PID health remained healthy while Beat was stopped for 46.6 seconds and during Redis loss, despite scheduler progress failure. |

## Current evidence boundaries

- PostgreSQL and SMTP do not provide exactly-once receipt; the product boundary is at most one application SMTP attempt.
- Chromium E2E is serial and destructive only inside its isolated project.
- Historical query-plan timings are host-sensitive regression tripwires, not an API/UI latency SLO.
- The historical recovery gate proves its isolated dump/replace/load primitive. It bypasses the defective public backup and restore pipelines and does not validate them.
- The ledger's [evidence-only gaps](development/functional-audit.md#evidence-only-gaps) and [refuted findings and allowed limits](development/functional-audit.md#refuted-findings-and-allowed-limits) are authoritative for the remaining boundaries.

The commands above are the post-remediation verification record. Earlier sections
remain historical evidence and should not be interpreted as the current release
status.
