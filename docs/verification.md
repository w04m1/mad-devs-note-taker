# Verification record

This page separates checks run on the original documentation baseline from later committed automated evidence. A command passing proves only what that command exercises.

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

## Committed automated evidence

The workstream command details and measured results are in the [QA log](development/qa.md) and [E2E log](development/e2e.md). The later final main-branch reconciliation is recorded in the [documentation decision log](development/documentation.md).

- The final main-branch `./scripts/test.sh` passed 18 safe backend tests with 27 deselected, then 27 isolated PostgreSQL/real-service tests with 18 deselected and zero skips. Its service phase passed the `0001` → head, head → `0001` → head, head → base → head migration cycles and `alembic check`. The frontend phase passed 30 tests across 12 files and the production build. Both images were built before tests, so the command did not reuse a stale application image.
- The real-service gate exercised the production SMTP sender against Mailpit and proved that a repeated delivery task leaves one message and one terminal `sent` row. It also exercised a real Celery worker through Redis and two uvicorn processes receiving one event through real Redis Pub/Sub.
- PostgreSQL concurrency tests proved single-winner authorization and the two permitted authorization-versus-delete outcomes. Deterministic tests also cover expired-lease recovery and classification of committed `attempt_started` work as `unknown`.
- `./scripts/test-recovery.sh` passed isolated PostgreSQL and Redis restart persistence and PostgreSQL logical dump, database replacement, restore, and row verification.
- The deterministic scale phase loaded exactly 10,000 notes and emitted retained JSON `EXPLAIN (ANALYZE, BUFFERS)` plans. The final main-branch `./scripts/test.sh` recorded calendar 0.087 ms, trigram search 17.06 ms, tag filter 6.473 ms, and trash 0.365 ms; all were below the gate's 500 ms regression ceiling.
- The isolated Playwright audit installed from its frozen lockfile, passed `tsc --noEmit`, and passed all six Chromium scenarios in 40.7 seconds. It covers cross-context realtime and Upcoming transitions, notification delivery/deduplication through Mailpit and Redis, timezone-sensitive calendar drag, stale-edit conflict handling, recurrence edit/delete/split, and cross-context trash/restore.

The final main-branch `./scripts/test.sh` did not rerun `./scripts/test-recovery.sh` or the Playwright suite. Recovery and E2E claims above remain limited to their existing committed logs.

## Manual integrated evidence

The integration log records a fresh-volume stack run with migrations through `0003_background`, seven healthy long-lived services, proxied readiness returning `{"status":"ok"}`, and an addressed worker `pong`.

A separate manual integrated check created note `ce69ad83-9f4c-4b47-b4d2-58f184cebf09` through the frontend proxy. Beat and the worker processed its due reminder. Mailpit contained exactly one message to `demo@example.test`, with stable `Message-ID` `24325b70-0336-4c8b-af5a-f414704229f9.1@notetaker.local`. Persistent notification `7d0d7910-745e-4a22-b441-18bb3fcda6cf` matched that delivery. The source record is [`docs/development/integration.md`](development/integration.md). This manual result supplements rather than substitutes for the automated SMTP evidence above.

## Explicit verification limits

- PostgreSQL and SMTP do not provide exactly-once receipt. The application promises at most one SMTP attempt. A worker was not SIGKILLed at every instruction boundary or specifically after Mailpit accepted `DATA`.
- Redis outage `resync_required` behavior is unit-tested but has not been black-box tested during an open connection. Live multi-process fanout is verified; replay across an outage is not claimed.
- Authorization was raced against note deletion, but not recurrence split or retention cleanup. Full application availability during a service outage is not covered by the isolated restart/persistence gate.
- The 500 ms query ceiling is a host-sensitive regression tripwire, not a latency SLO. Hardware percentiles and materialization of exactly 10,000 recurrence occurrences are not claimed.
- Browser E2E is Chromium-only, serial, and destructive within its isolated Compose project. Duplicate-toast observation is bounded to 600 ms, and scheduled-delivery polling does not simulate prolonged retries or broker outages.
- Full TypeScript DTO generation from OpenAPI is not present. Focused OpenAPI shape tests cover high-risk endpoints only.
