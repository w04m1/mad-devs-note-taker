# Final documentation decision log

## 2026-09-09 — Separate the plan from implementation status

- **Decision:** Add `docs/implementation-status.md` and link it prominently from the README. Treat `PLAN.md` as intended architecture and test scope, not proof of completion.
- **Reason:** The plan is broader than any single verification command, so implementation claims must be tied to committed evidence rather than unchecked plan items.
- **Evidence:** The initial code audit found implemented HTTP, recurrence, background, realtime, and frontend modules. Later E2E and QA evidence is reconciled in the entries below.
- **Limit:** Work without committed evidence remains unclaimed; later committed evidence supersedes the initial baseline where stated below.

## 2026-09-09 — Use evidence tiers in the verification record

- **Decision:** Separate commands executed on the current application baseline, integrated runtime records, and unverified work. Include exact pass/skip counts and the scope of each command.
- **Reason:** A healthy Compose stack, unit tests, PostgreSQL integration tests, and browser tests prove different things. Combining them would overstate coverage.
- **Evidence:** Fresh documentation-audit runs produced Compose validation, backend lint, 18 local backend passes with 19 database skips, 28 frontend passes, a frontend build, and a full stack smoke pass.
- **Limit:** The smoke script checks service/process and HTTP wiring. It does not create a note or exercise SMTP.

## 2026-09-09 — Record real reminder evidence as manual

- **Decision:** Cite the integration log's note ID, Mailpit `Message-ID`, recipient, exact-one count, and matching notification. Keep it labeled as manual evidence distinct from the later automated real-SMTP result.
- **Reason:** The result proves the deployed proxy/Beat/worker/SMTP/notification path once, but its manual nature and boundary remain relevant even after automated service coverage was added.
- **Evidence:** `docs/development/integration.md`, entry `2026-09-09T19:25:46Z`.
- **Limit:** Exactly-once SMTP receipt is not promised; ambiguous outcomes follow the documented at-most-one application-attempt policy.

## 2026-09-09 — Surface user-visible and contract limits

- **Decision:** Put user-visible DST behavior, the large frontend chunk, partial OpenAPI coverage, and the exact boundary of E2E/QA evidence in status and verification where applicable. Mention the build warning in the README.
- **Reason:** These are material implementation or evidence boundaries. Operators and reviewers should not need to infer them from workstream logs.
- **Evidence:** The initial audited build produced a 793.95 kB minified main JS chunk and frontend DTOs are handwritten. The later manual-overlap and E2E outcomes are recorded below.
- **Limit:** Bundle size is a build warning, not a build failure. Focused OpenAPI tests reduce risk but do not generate a complete client.

## 2026-09-09 — Document two supported command paths

- **Decision:** Make Docker Compose the primary setup. Also list fast native backend and frontend commands with their prerequisites and database-skip behavior.
- **Reason:** Compose supplies the reproducible full environment, while native commands give quick feedback during development.
- **Evidence:** The listed commands match `compose.yaml`, `scripts/*.sh`, `backend/pyproject.toml`, and `frontend/package.json` and were exercised during this audit.
- **Limit:** Native backend pytest without `TEST_DATABASE_URL` skips PostgreSQL tests; use `./scripts/test.sh` for Compose-backed execution.


## 2026-09-09 — Reconcile the six-scenario E2E audit

- **Decision:** Replace the pending E2E statement with the committed clean-audit result: frozen install and TypeScript checking passed, followed by six passing Chromium scenarios in 40.7 seconds.
- **Reason:** `tests/e2e` and its execution record are now present on this branch, so the placeholder-era status is no longer accurate.
- **Evidence:** `docs/development/e2e.md` records the isolated Compose command, fresh volumes, healthy services, teardown, scenario mapping, and timings.
- **Limit:** The suite is Chromium-only, serial, and destructive within its selected isolated project. Its 600 ms duplicate window and 12–15 second delivery polls do not prove prolonged retry or broker-outage behavior.

## 2026-09-09 — Promote committed real-service QA evidence

- **Decision:** Record automated production-path SMTP/Mailpit, Celery/Redis, and multi-process WebSocket fanout as verified rather than pending. Also record the single-winner and authorization-versus-delete race results.
- **Reason:** The isolated service gate exercises these boundaries directly and fails on a skipped selected test.
- **Evidence:** `docs/development/qa.md` records 17 service tests passed with zero skips. A repeated production `deliver` call left one Mailpit message and one `sent` row; a real worker committed work sent through Redis; two uvicorn processes received the same Redis event.
- **Limit:** The gate does not SIGKILL workers at each instruction boundary. Redis outage behavior is not black-box tested on an open socket. Authorization has not been raced against recurrence split or retention cleanup.

## 2026-09-09 — Record recovery and deterministic scale results

- **Decision:** Replace the general pending restart/performance statements with the exact automated results that are committed.
- **Reason:** The recovery and query-plan gates now have final isolated records, but their narrower boundary must not be inflated into full outage or latency claims.
- **Evidence:** `./scripts/test-recovery.sh` preserved PostgreSQL and Redis sentinels across restart and verified a PostgreSQL logical dump/replace/restore cycle. The scale gate loaded exactly 10,000 deterministic notes and retained analyzed JSON plans for calendar, trigram search, tag filter, and trash; all recorded execution times were below 500 ms.
- **Limit:** Recovery does not prove full application availability during outage or a worker kill after Mailpit accepts `DATA`. The 500 ms ceiling is a host-sensitive regression tripwire, not an SLO; hardware percentiles and 10,000-occurrence recurrence materialization remain unclaimed.

## 2026-09-09 — Treat manual DST overlap selection as implemented

- **Decision:** Move ordinary-note DST overlap handling out of deviations and into implemented behavior. The form presents both offset-qualified occurrences, selects neither by default, blocks save until the user chooses, and sends the chosen instant unchanged. Preserve the separate recurrence rule that selects the earlier instant.
- **Reason:** The explicit accessible selector resolved the earlier behavior that silently chose the first overlap occurrence.
- **Evidence:** `docs/development/contract-hardening.md` and `docs/development/final-correctness.md` record the implementation and focused tests for the Budapest gap and overlap, including selection of the second `+01:00` occurrence.
- **Limit:** Spring-forward gaps remain rejected by design; this decision does not alter recurrence expansion semantics.

## 2026-09-09 — Reconcile the final main-branch complete gate

- **Decision:** Update the public record from the older QA-log snapshot to the just-completed main-branch `./scripts/test.sh`: 18 safe backend tests passed with 27 deselected; 27 PostgreSQL/real-service tests passed with 18 deselected and zero skips; all migration cycles and `alembic check` passed; 30 frontend tests across 12 files and the production build passed. Record the same run's query times exactly: calendar 0.087 ms, trigram search 17.06 ms, tag filter 6.473 ms, and trash 0.365 ms.
- **Reason:** The final recurrence and DST hardening increased both backend and frontend coverage after the earlier 17/17/25 result. Keeping the older counts as the current result would understate the tested main branch.
- **Evidence:** The completed root gate built both images before testing and ran the safe, isolated service/migration/scale, frontend unit, and frontend build phases successfully.
- **Limit:** `./scripts/test.sh` does not invoke `./scripts/test-recovery.sh` or `tests/e2e/run.sh`. This reconciliation does not claim a new recovery or Playwright rerun; those claims remain tied to the existing committed QA and E2E logs.
