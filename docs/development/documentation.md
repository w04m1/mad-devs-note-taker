# Final documentation decision log

## 2026-09-09 — Separate the plan from implementation status

- **Decision:** Add `docs/implementation-status.md` and link it prominently from the README. Treat `PLAN.md` as intended architecture and test scope, not proof of completion.
- **Reason:** The plan includes generated DTOs, browser E2E, performance, and resilience work whose final results are not present on this branch.
- **Evidence:** The code audit found implemented HTTP, recurrence, background, realtime, and frontend modules, while `tests/e2e` contains only `.gitkeep` on this branch.
- **Limit:** Active branch work is deliberately described as pending rather than passed or failed.

## 2026-09-09 — Use evidence tiers in the verification record

- **Decision:** Separate commands executed on the current application baseline, integrated runtime records, and unverified work. Include exact pass/skip counts and the scope of each command.
- **Reason:** A healthy Compose stack, unit tests, PostgreSQL integration tests, and browser tests prove different things. Combining them would overstate coverage.
- **Evidence:** Fresh documentation-audit runs produced Compose validation, backend lint, 18 local backend passes with 19 database skips, 28 frontend passes, a frontend build, and a full stack smoke pass.
- **Limit:** The smoke script checks service/process and HTTP wiring. It does not create a note or exercise SMTP.

## 2026-09-09 — Record real reminder evidence as manual

- **Decision:** Cite the integration log's note ID, Mailpit `Message-ID`, recipient, exact-one count, and matching notification. Label the result manual and keep automated real-SMTP coverage pending.
- **Reason:** The result proves the deployed proxy/Beat/worker/SMTP/notification path once, but it is not a repeatable regression result and does not prove failure boundaries.
- **Evidence:** `docs/development/integration.md`, entry `2026-09-09T19:25:46Z`.
- **Limit:** Exactly-once SMTP receipt is not promised; ambiguous outcomes follow the documented at-most-one application-attempt policy.

## 2026-09-09 — Surface user-visible and contract limits

- **Decision:** Put the manual DST-overlap selector deviation, large frontend chunk, partial OpenAPI coverage, and pending E2E/QA evidence in both status/verification where applicable. Mention the build warning in the README.
- **Reason:** These are material gaps between the current repository and the full plan. Operators and reviewers should not need to infer them from workstream logs.
- **Evidence:** The current note form selects the earlier overlap; the audited build produced a 793.95 kB minified main JS chunk; frontend DTOs are handwritten; the E2E suite is not merged here.
- **Limit:** Bundle size is a build warning, not a build failure. Focused OpenAPI tests reduce risk but do not generate a complete client.

## 2026-09-09 — Document two supported command paths

- **Decision:** Make Docker Compose the primary setup. Also list fast native backend and frontend commands with their prerequisites and database-skip behavior.
- **Reason:** Compose supplies the reproducible full environment, while native commands give quick feedback during development.
- **Evidence:** The listed commands match `compose.yaml`, `scripts/*.sh`, `backend/pyproject.toml`, and `frontend/package.json` and were exercised during this audit.
- **Limit:** Native backend pytest without `TEST_DATABASE_URL` skips PostgreSQL tests; use `./scripts/test.sh` for Compose-backed execution.
