# Verification record

This page separates checks run on the current documentation baseline from historical manual evidence. A command passing proves only what that command exercises.

## Current baseline checks (2026-09-09)

Run from repository revision `26257ff` before the documentation commits:

| Check | Result | Boundary |
|---|---|---|
| `./scripts/compose-config.sh` | Pass | Compose parses and normalizes. |
| `cd backend && uv run --frozen ruff check .` | Pass | Ruff checks the current backend tree. |
| `cd backend && uv run --frozen pytest` | 18 passed, 19 skipped, 2 dependency deprecation warnings | The skipped tests require `TEST_DATABASE_URL`; this run is not PostgreSQL integration evidence. |
| `cd frontend && corepack pnpm test` | 28 passed in 12 files | Component/unit tests only; not browser E2E. |
| `cd frontend && corepack pnpm build` | Pass; 2,086 modules transformed | Main JS chunk was 793.95 kB minified (240.31 kB gzip), above Vite's 500 kB warning threshold. |
| `./scripts/smoke.sh` | Pass | Built and started the stack, completed migration, found exactly seven running services, and reached the frontend, proxied readiness endpoint, and Mailpit API. It did not create product data or send email. |

The backend test run used Python 3.12.10. The frontend run used pnpm 11.21.0 and Vite 8.2.2.

## Integrated runtime evidence

The integration log records a fresh-volume stack run with migrations through `0003_background`, seven healthy long-lived services, proxied readiness returning `{"status":"ok"}`, and an addressed worker `pong`.

A separate **manual** integrated check created note `ce69ad83-9f4c-4b47-b4d2-58f184cebf09` through the frontend proxy. Beat and the worker processed its due reminder. Mailpit contained exactly one message to `demo@example.test`, with stable `Message-ID` `24325b70-0336-4c8b-af5a-f414704229f9.1@notetaker.local`. Persistent notification `7d0d7910-745e-4a22-b441-18bb3fcda6cf` matched that delivery. The source record is [`docs/development/integration.md`](development/integration.md).

This is real SMTP-path evidence, but it is not an automated regression. It does not prove crash recovery, Redis outage behavior, high-contention locking, or exactly-once receipt. The design intentionally promises at most one application SMTP attempt, not exactly-once receipt.

## Not yet verified on this baseline

- The six planned Playwright scenarios are not in this branch (`tests/e2e` contains only its placeholder). Work and results on active E2E branches are pending integration and review; no browser scenario is claimed as passing here.
- Final QA results for restart/failure behavior, multi-process WebSocket fanout, performance with several thousand notes, and contention are pending.
- Automated real-SMTP coverage is pending. The current automated sender tests use a fake/monkeypatched SMTP boundary.
- Full TypeScript DTO generation from OpenAPI is not present. Focused OpenAPI shape tests cover high-risk endpoints only.
