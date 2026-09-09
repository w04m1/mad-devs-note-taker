# Frontend development decision log

This file records frontend implementation decisions. The shared API contract in `docs/contracts.md` remains authoritative.

## 2026-09-09 — Wave 2 frontend foundation

### React, Vite, TypeScript, and dependency pinning

**Decision:** Use React 19 with Vite 8, strict TypeScript project references, pnpm 11, and exact package versions. Commit `pnpm-lock.yaml`. The app uses the Vite Tailwind plugin and imports Tailwind CSS v4 from the main stylesheet.

**Alternatives:** Create React App was rejected because it is no longer the requested toolchain. Version ranges were rejected because they make fresh installs drift. Tailwind v3/PostCSS was not selected because the current Vite plugin removes separate PostCSS configuration.

**Evidence:** `pnpm peers check` passes. Production build and typecheck commands are recorded in this entry's verification section. Tailwind's current Vite installation was checked through Context7 before setup.

### Server state and navigation ownership

**Decision:** TanStack Query owns remote state. React Router owns screen routing. URL parameters will own list/calendar controls as features land. The shell exposes Calendar, Notes, Upcoming, Trash, Tags, Notifications, and Settings routes now, including a catch-all page. There is no client-side global data store.

**Alternatives:** A Redux/Zustand store was rejected because it would duplicate the query cache. A single conditional screen component was rejected because real URLs are required for filters and navigation.

**Evidence:** TanStack Query v5 documentation confirms prefix query invalidation and `QueryClientProvider`. Route smoke behavior is covered by semantic screen headings and the production build.

### API types and runtime validation boundary

**Decision:** Keep contract-shaped TypeScript DTOs and one central `request` function under `src/api`. It handles relative `/api/v1` URLs and structured errors. Repeated query values use repeated keys. Zod validates user-authored form data only; it does not define a competing runtime API schema. Generated OpenAPI DTOs may replace the handwritten contract-shaped interfaces when backend OpenAPI is published.

**Alternatives:** Parsing every response with separate Zod schemas was rejected because it can drift from OpenAPI. Direct `fetch` calls in screens were rejected because error and header behavior would diverge.

**Evidence:** Contract tests cover repeated `tag_id` values and the `409` error shape. Types match the frozen `docs/contracts.md`, including `active`, full replacement arrays, versions, and reminder values `10 | 60 | 1440`.

### Accessible component foundation

**Decision:** Use small shadcn-style source-owned primitives built with Radix Slot/Dialog, CVA, Tailwind Merge, native labels, focus-visible styles, semantic landmarks, and an `aria-live` toast region. Keep `components.json` for future shadcn additions.

**Alternatives:** A large pre-styled component suite was rejected to keep control of markup and avoid duplicate styling systems. A custom modal was rejected because focus management and escape behavior are easy to get wrong.

**Evidence:** Radix Dialog supplies focus trapping, accessible title/description wiring, escape handling, and focus return. Inputs retain native label association and errors use `role=alert`.

### Form foundation

**Decision:** Use React Hook Form with the Zod resolver. Initial Zod schemas cover notes, tags, settings, and search. Offset-qualified note datetimes, unique preset reminders, valid UUID tag IDs, hex colors, email, and the three-character search rule are validated before submission.

**Alternatives:** Component-local ad hoc checks were rejected because they scatter rules. Using API DTOs as form state without a validation layer was rejected because drafts can be incomplete.

**Evidence:** Unit tests cover search length, reminder uniqueness/presets, and required datetime offsets.

### Calendar dependency boundary

**Decision:** Pin FullCalendar month, time-grid, interaction, React, and Luxon 3 plugins as a coherent 6.1.21 set. Calendar feature code will import them when calendar behavior is implemented.

**Alternatives:** A hand-built calendar was rejected due to keyboard, drag, and timezone complexity. Browser-only date formatting was rejected for the named-zone behavior required by the plan.

**Evidence:** `pnpm peers check` reports no peer dependency issues. The plan cites FullCalendar's Luxon named-zone guidance.

### Realtime invalidation, reconnect, and toast deduplication

**Decision:** Treat WebSocket events as invalidation signals only. A central mapping invalidates all affected query families. `resync_required` invalidates the whole cache. Each connection ignores duplicate event IDs with a bounded 1,000-item set. Disconnects reconnect with exponential backoff, 20% jitter, and a 30-second cap. While disconnected, a 30-second timer reconciles active queries. A successful reconnection resets the attempt counter, stops reconciliation, and immediately invalidates active queries. Live notification events older than the 60-second grace window are not toasted.

For `notification.created`, `entity_id` is the notification ID used for toast deduplication in tab-scoped `sessionStorage`. The live event only emits the generic text “A reminder is due”; notification details remain authoritative in the history API. Loading notification history never emits a toast.

**Alternatives:** Applying event payloads directly to cached entities was rejected because events are not authoritative state. `localStorage` was rejected because deduplication is required per tab. Unbounded ID retention was rejected due to memory growth. Fixed-delay reconnect was rejected because many clients could reconnect together.

**Evidence:** Unit tests cover malformed events, dependent query-family mapping, and full invalidation. The event fields and behaviors follow `docs/contracts.md`; using `entity_id` avoids adding an undocumented payload.

### Development proxy and deployment boundary

**Decision:** Browser code always calls relative `/api/v1` and `/ws`. Vite proxies both to `backend:8000` and enables WebSocket forwarding. This keeps same-origin behavior in local Compose and production-like environments.

**Alternatives:** A compiled backend host environment variable was rejected because it creates avoidable CORS differences. Direct backend hostnames are not resolvable from normal browsers in Compose.

**Evidence:** The proxy matches the environment section of `PLAN.md`. The API-client unit test asserts the relative URL.

### Verification

Run from `frontend/`:

- `pnpm install --frozen-lockfile`
- `pnpm peers check`
- `pnpm typecheck`
- `pnpm test`
- `pnpm build`
