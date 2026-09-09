# E2E development log

## 2026-09-09 — Playwright full-stack harness and six scenarios

### Harness decisions

- Added a self-contained pnpm project in `tests/e2e` with pinned Playwright 1.52.0, TypeScript 5.8.3, and a frozen lockfile. This avoids changing frontend runtime dependencies.
- `run.sh` starts all seven long-lived services plus migration with Compose project `notetaker-e2e`. It uses host ports 15173 and 18025, destroys its named volumes by default, and supports `E2E_KEEP_STACK=1` for diagnosis.
- Tests run serially with one worker because the application intentionally has one shared profile. Each test truncates application tables through `docker compose exec postgres`; there is no production reset or fake-clock API.
- Fixtures create notes and series over the real proxied HTTP API. Key edits, drag, stale save, trash, restore, occurrence edit, and series split use browser controls.
- Cross-client cases create separate browser contexts, not only separate pages. Calendar uses browser timezone `Asia/Tokyo` while profile timezone is `America/Los_Angeles`.
- Reminder evidence crosses the worker, Beat, Redis, PostgreSQL, WebSocket, SMTP, and Mailpit. The duplicate notification is injected into the real Redis Pub/Sub channel. Delivery eligibility is inspected in PostgreSQL after UI trash/restore.
- All waits are bounded. Normal expectations use 8 seconds. Due reminders and Mailpit use explicit 12–15 second polling windows. No fixed sleeps are used except a bounded 600 ms duplicate-event observation window.
- Playwright retains trace, screenshot, and video only on failure. The wrapper also saves the last 200 Compose log lines when a run fails.
- The suite is serial and destructive only to its isolated Compose project. Changing `E2E_COMPOSE_PROJECT` to a non-isolated running project is unsafe.

### Scenario mapping

1. **Realtime and Upcoming:** UI edit in context A, WebSocket-driven title update in context B, then the scheduled note crosses into Past active without reload.
2. **Notifications:** two live tabs get one toast each; PostgreSQL history and Mailpit each contain one record; Redis repeats the same notification identity; refresh does not replay it.
3. **Calendar:** month event is dragged by UI with mismatched browser/profile zones; API instant keeps profile-local time and reload keeps the target day.
4. **Concurrent editing:** two contexts open one version; A saves, B keeps a dirty body, stale save shows the explicit conflict and still keeps the draft.
5. **Recurrence:** an occurrence is edited through the scope chooser, the next is trashed, and a later occurrence splits future UI; API checks earlier edit/cancellation and successor replacement.
6. **Trash/restore:** context A trashes and context B observes/restores; normal views update over WebSocket; PostgreSQL proves cancelled future work becomes pending again with no past deadline.

### Evidence and current execution limit

- `corepack pnpm install --frozen-lockfile` succeeds.
- `corepack pnpm run typecheck` succeeds for the E2E project.
- An actual `./tests/e2e/run.sh --grep concurrent` run on 2026-09-09 built the images and created isolated fresh volumes, then stopped before Playwright because migration `0001` exited 1: PostgreSQL reported `relation "ix_notes_purged_at" already exists`. The model currently declares both `purged_at` with `index=True` and an explicit index of the same name. The wrapper removed the failed project and volumes as designed; `artifacts/compose.log` held the service traceback.
- After the migration blocker is fixed, full browser execution is also expected to encounter an integrated frontend/backend contract mismatch already assigned to the contract-hardening workstream: `/api/v1/tags` returns an array while the current frontend reads `data.items`, so `/notes` crashes before UI actions. Upcoming also currently differs (`today/week/past` are paged backend groups while the frontend expects arrays and `this_week`). No product-code workaround was committed here so the contract owner remains authoritative.
- After that integration fix lands, run `./tests/e2e/run.sh`. Any remaining selector or timing failures must be reported from actual artifacts rather than claimed as passing.
