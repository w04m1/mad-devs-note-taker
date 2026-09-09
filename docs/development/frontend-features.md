# Frontend feature wave decision log

This log covers `codex/frontend-features`. Entries are chronological. The shared contract in `docs/contracts.md` is the authority unless an integration finding is stated explicitly.

## 2026-04-09 — Keep server query state separate from the note draft

**Decision.** Notes use TanStack Query keys containing every applied filter, sort, and page value. The editor copies a selected note into component-owned state only when the editor mounts. Query invalidation does not reset that state.

**Why/evidence.** Realtime events invalidate note queries. Resetting from each new query result can silently destroy typing. The component test rerenders with a newer remote version and verifies that the local title remains.

**Alternatives.** Binding inputs directly to cached data was rejected because invalidation would overwrite a dirty draft. A global draft store was rejected because the application only needs one open editor.

**Deviation.** Filters are kept in component state rather than the URL. URL persistence is useful but is not part of the frozen contract or this feature wave.

## 2026-04-09 — Use an explicit search submit

**Decision.** Blank searches are omitted. Nonblank searches must pass the existing three-character schema. Applying search or changing any filter/sort resets the page to one. Search is submitted rather than debounced.

**Why/evidence.** This prevents invalid server requests and avoids issuing one request per keystroke across several thousand notes. The API client test proves repeated query values are serialized correctly.

**Alternatives.** A debounce with abort propagation was considered. It adds request cancellation work without a requirement for live-as-you-type search. Explicit submit is deterministic and accessible.

## 2026-04-09 — Treat writes as versioned full replacements

**Decision.** Note updates always send title, body, start, active state, all tag IDs, all reminder offsets, and `expected_version`. For recurring notes, the UI first fetches the series and includes `expected_series_version` for update, trash, and restore.

**Why/evidence.** The frozen contract defines replacement semantics and requires both aggregate versions for series occurrences. Sending partial UI changes could accidentally clear or overwrite associations.

**Alternatives.** Optimistic cache writes were rejected. They complicate rollback and can display state that the version check rejects.

## 2026-04-09 — Preserve drafts and stop on HTTP 409

**Decision.** A 409 never retries and never closes the form. The conflict panel states that the note changed elsewhere, keeps all local values, and exposes the server `current` value. The user must cancel and reopen to intentionally load current state.

**Why/evidence.** The contract prohibits silent concurrent overwrite. The conflict test submits a dirty title against a 409 and checks that both the warning and dirty value remain.

**Alternatives.** Automatic last-write-wins and automatic form reset were rejected as data-loss paths. Field-level merging was not chosen because arbitrary note body merges need product rules that do not exist.

## 2026-04-09 — Convert wall time with the saved IANA zone

**Decision.** `datetime-local` values are interpreted with Luxon in the saved settings timezone and sent as offset-qualified ISO 8601. Existing instants are converted into that zone before editing.

**Why/evidence.** Browser-local `Date` conversion would use the machine zone, which can differ from the profile zone. The contract requires offset-qualified datetimes and says timezone changes affect display rather than stored instants.

**Alternatives.** Sending a zone-less local string fails validation. Treating all local inputs as UTC gives incorrect instants outside UTC.

## 2026-04-09 — Centralize mutation invalidation

**Decision.** `useNoteMutations`, `useTagMutations`, and `useSettingsMutation` own API calls and cache reconciliation. Note writes invalidate notes, calendar, upcoming, and trash. Tag writes invalidate tags plus notes, calendar, and upcoming because all can render tag metadata. Settings writes update settings and invalidate time-rendering views.

**Why/evidence.** The same actions are used by list cards, forms, and Trash. One policy prevents screens from forgetting dependent caches. Mutations have no automatic retry.

**Alternatives.** Duplicated screen-local mutations were rejected. Broad `invalidateQueries()` was rejected because it would refetch unrelated history and profile requests.

## 2026-04-09 — Keep destructive actions explicit

**Decision.** Note trash and tag delete require browser confirmation. Trash is a dedicated paged `trash=true` query and restoration carries the current note and optional series versions.

**Why/evidence.** Tag deletion changes associations and note deletion affects reminders. Accidental clicks should not immediately mutate server state.

**Alternatives.** An undo toast was considered, but no inverse endpoint exists for tag deletion. A custom confirmation dialog can replace `confirm` in a later visual-polish wave.

## 2026-04-09 — Make tags and settings small inline forms

**Decision.** Tag create/edit shares one form with schema validation and explicit cancel. Settings initializes once from fetched values and remains mounted through invalidations, so a failed/409 save preserves edits. Settings explains that timezone does not reschedule stored instants.

**Why/evidence.** These records have few fields. Inline forms reduce modal state while keeping version checks visible in request behavior.

**Alternatives.** Separate create and edit routes were rejected as excess navigation for two-field records.

## 2026-04-09 — Render notification history without toast coupling

**Decision.** Notification history is a normal paged query. It never invokes the toast API. The UI renders `scheduled_at`, `created_at`, title, and persistent record identity.

**Why/evidence.** The realtime contract states history must never replay live toasts. Inspection of the backend HTTP schema found `scheduled_at`, while the initial frontend type used `scheduled_for`; the frontend was aligned to the backend implementation.

**Alternatives.** Keeping `scheduled_for` was rejected because integration would render an invalid date. This is an additive clarification to the shared document, which did not freeze notification field names.

## 2026-04-09 — Validation and test scope

**Decision.** This wave adds interaction tests for dirty-draft preservation and the complete 409 path. Existing schema, API serialization/error, realtime invalidation, and route tests remain the supporting coverage. Frozen install, TypeScript, Vitest, and production build are the release gates.

**Why/evidence.** The highest-risk behavior is concurrency-driven data loss. Pure list rendering adds less risk and is covered by typed contracts and build checks.

**Known scope boundary.** Calendar and Upcoming remain integration placeholders. This wave implements the requested Notes, tags, Trash, settings, and notification-history surfaces. Recurrence series creation/splitting UI belongs to its planned recurrence/calendar wave; this wave only makes occurrence mutations version-safe.
