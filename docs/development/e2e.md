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

- The focused frontend contract fix is present as `08405a3`: tags consume the backend array and Upcoming consumes paged `today`, `week`, and `past` groups.
- Audit command: `E2E_COMPOSE_PROJECT=notetaker-e2e-audit FRONTEND_PORT=25173 MAILPIT_UI_PORT=28025 E2E_BASE_URL=http://127.0.0.1:25173 E2E_MAILPIT_PORT=28025 ./tests/e2e/run.sh`.
- The audit used a new Compose project and fresh named PostgreSQL and Redis volumes. Migration exited 0. Compose reported every long-lived service healthy. The wrapper removed the containers, network, and volumes after the run.
- Dependency install with the frozen lockfile and `tsc --noEmit` both exited 0.
- Chromium result: **6 passed (40.7s)**. Scenario durations were realtime/Upcoming 11.2s, notification 12.4s, calendar 2.9s, concurrent editing 5.6s, recurrence 3.4s, and trash/restore 4.2s.
- No harness or selector defect appeared in the clean audit, so no test behavior was loosened. Broader contract-hardening changes were not pulled into this branch because they are outside the E2E harness scope and were not needed for these six scenarios.
- Limits: the suite remains Chromium-only, serial, and destructive within its selected Compose project. The duplicate-toast observation is intentionally bounded to 600 ms. The test proves one scheduled delivery during its polling window, not behavior under prolonged retries or broker outages.
