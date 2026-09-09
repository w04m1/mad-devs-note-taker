# Frontend calendar, Upcoming, recurrence, and Notes URL state

## 2026-06-03 — implementation record

This log covers the `codex/frontend-calendar` workstream. Each item records the decision, the alternative considered, and the evidence or constraint that drove it.

### Calendar data and navigation

- **Decision:** FullCalendar uses `dayGridMonth`, `timeGridWeek`, `timeGridDay`, `interaction`, and `luxon3`, with the saved settings IANA timezone passed to `timeZone`. **Alternative:** browser-local rendering or manual calendar grids. **Evidence:** PLAN section 11 requires FullCalendar plus named-zone Luxon rendering and month/week/day views.
- **Decision:** `datesSet` owns the half-open `starts_from`/`starts_to` request and the calendar query key includes the range. A client guard refuses ranges over 93 elapsed days. **Alternative:** preload the Notes list and filter it in the browser. **Evidence:** `/calendar` is the authoritative bounded endpoint and the plan caps requests at 93 days.
- **Decision:** the URL owns `view` and visible `date`; invalid values fall back to month and today in the saved timezone. FullCalendar initializes from these values, while an imperative ref applies later URL changes so Back/Forward navigation also changes the mounted calendar. **Alternative:** component-only state or initial-prop-only URL support. **Evidence:** PLAN section 11 assigns calendar view/date to URL parameters, which must support links and browser history.
- **Decision:** events remain timed points (`allDay: false`, no editable duration). **Alternative:** synthesize one-hour blocks or persist all-day state. **Evidence:** the frozen contract says visual blocks must not add stored duration or all-day semantics.

### Calendar drag and open behavior

- **Decision:** drag conversion uses FullCalendar's offset-qualified `event.startStr`, parses it with Luxon, and sends a UTC ISO instant. **Alternative rejected:** reconstruct wall-clock fields from `Date#getHours()`, which silently uses the browser zone and is wrong when it differs from the saved zone. **Evidence:** a DST test verifies `2026-10-25T02:30:00+02:00` in `Europe/Budapest` becomes `2026-10-25T00:30:00Z`.
- **Decision:** an ordinary or single-occurrence move sends full replacement note fields with `expected_version`; recurring occurrences first read the current series version and also send `expected_series_version`. **Alternative:** optimistic cache-only move or unversioned patch. **Evidence:** the contract requires versioned mutations and forbids silent overwrites.
- **Decision:** cancel, validation failure, HTTP failure, and 409 invoke FullCalendar `revert`; cancellation and failures invalidate calendar, Notes, and Upcoming. **Alternative:** leave the optimistic position visible or revert without reconciling authoritative state. **Evidence:** PLAN explicitly requires revert and refetch. Component tests prove both 409 and dialog cancellation restore and refetch.
- **Decision:** clicking an event opens the shared note editor. A recurring event first asks `Only this occurrence` or `This and future occurrences`. **Alternative:** always edit one occurrence. **Evidence:** recurrence scope must be explicit.

### Recurrence creation and future editing

- **Decision:** Notes exposes separate `New note` and `New series` actions. Series creation collects the full note template, local start, recurrence zone, daily/weekly/monthly frequency, required inclusive end date, tags, reminders, and active state. **Alternative:** overload the ordinary note form with hidden recurrence controls. **Evidence:** separate actions keep the common form short and make the finite-series requirement visible.
- **Decision:** manual local values convert with Luxon in the recurrence/profile IANA zone. A wall-clock round trip rejects a nonexistent initial local time instead of accepting Luxon’s forward normalization; an ambiguous initial time chooses the earlier instant, matching the recurrence contract. Generated invalid monthly dates and later nonexistent DST slots remain backend-skipped. **Alternative:** `new Date(datetime-local)` in the browser zone or silent normalization through a spring-forward gap. **Evidence:** recurrence is defined in its own named timezone, and the frozen contract selects the earlier overlap instant. Unit tests cover the Budapest 2026 gap and overlap.
- **Decision:** future editing fetches the series before mounting the form and initializes frequency, end date, and recurrence timezone from it. **Alternative rejected:** initialize from profile timezone and a weekly default, which could unintentionally change a series. **Evidence:** `Note` does not include the series definition.
- **Decision:** the future editor and future drag display an explicit warning that later individual edits, moved dates, and cancellations are replaced while earlier history stays. **Alternative:** generic confirmation text. **Evidence:** this consequence is an agreed product decision. A test requires the warning before the future form appears.
- **Decision:** future writes use the current handwritten `SeriesSplit` DTO (`expected_version` for series plus `expected_occurrence_version`). **Deviation/gap:** PLAN prose sometimes calls the former `expected_series_version`; backend routes are not present in this worktree, so end-to-end verification is blocked. The frontend follows `docs/contracts.md` plus the existing TypeScript client without inventing another route.
- **Known contract gap:** `SeriesCreate` carries both `starts_at` and `local_start`; the UI keeps them consistent by deriving both from the same Luxon value. The backend must validate or define precedence.

### Upcoming transitions

- **Decision:** Today, This week, and Past active are separate accessible sections; each note is a button that opens the same scope-aware editor. **Alternative:** duplicate edit UI or passive cards. **Evidence:** the requirements say notes must move groups and remain editable/openable.
- **Decision:** refresh delay is computed from backend `server_now`, not the browser clock, choosing the earlier of `next_transition_at` and the next midnight in the saved timezone. **Alternative:** subtract `Date.now()`, which makes skewed clients transition early or late. **Evidence:** backend transition metadata is authoritative; tests cover clock skew and a DST boundary.
- **Decision:** schedule a one-shot transition timer, a 60-second fallback interval, and immediate invalidation on window focus or return to visible state. The effect reschedules when either `server_now` or `next_transition_at` changes, and all listeners/timers are cleaned up. **Alternative:** interval only, or retaining a timer calculated from stale server metadata. **Evidence:** PLAN requires all four triggers and accounts for browser throttling; a fake-timer test covers transition, focus, fallback, and cleanup.
- **Known contract gap:** the frozen handwritten `UpcomingResponse` contains unpaged arrays even though PLAN calls the groups paginated. This implementation follows the shared DTO and does not guess query/paging fields. Large `past` groups remain a backend-contract issue.

### Notes URL filters and search

- **Decision:** `q`, repeated `tag_id`, `active`, period instants, `sort`, `direction`, `page`, and `page_size` round-trip through `useSearchParams`. Invalid URL values safely fall back to defaults. All filters except page reset to page 1. **Alternative:** retain component state. **Evidence:** PLAN assigns filters/sort/pagination to the URL. Codec tests cover repeated tags and invalid values.
- **Decision:** tags use an accessible multi-select because the server contract uses AND semantics for all selected tags. **Alternative:** the previous single-tag select. **Evidence:** the previous UI could not represent the documented filter.
- **Decision:** datetime-local period values convert with Luxon in saved settings timezone. **Alternative rejected:** the previous `new Date(value)` browser-zone conversion. **Evidence:** display grouping and filtering use the profile timezone.
- **Decision:** search validates the three-character minimum, waits 300 ms, updates the URL, and resets pagination. The timer applies its search value to the latest URL parameters rather than a captured snapshot, so a concurrent filter change is preserved. TanStack Query supplies an `AbortSignal` to `api.notes.list`, so a changed query cancels the obsolete fetch. **Alternative:** submit-only search, stale-snapshot debounce, or debounce without request cancellation. **Evidence:** PLAN requires approximately 300 ms and cancellable obsolete requests.

### Accessibility and shared UI

- **Decision:** Radix Dialog was expanded into controlled primitives while keeping its original trigger/title wrapper API. Cancelling or dismissing a pending recurring drag restores the event before closing. **Alternative:** hand-built overlays or a scope popup without dialog semantics. **Evidence:** controlled drag/scope dialogs need programmatic close and Radix supplies focus trapping, Escape handling, accessible names, and focus restoration; a test finds the scope chooser by its dialog name and verifies cancel invokes FullCalendar revert.
- **Decision:** errors use `role=alert`, loading uses `role=status`, busy calendar/recurrence/Upcoming regions expose `aria-busy`, Upcoming changes use `aria-live=polite`, note cards are native buttons, and rendered times include machine-readable `dateTime`. **Alternative:** clickable `div` elements or visual-only busy/time state. **Evidence:** keyboard and screen-reader access is required.

### Verification evidence

- `pnpm install --frozen-lockfile`: passed; the lockfile was already current.
- `pnpm typecheck`: passed.
- `pnpm test`: 11 files and 25 tests passed. Coverage includes named-zone DST drag conversion, version payload/revert/refetch on conflict, accessible recurring-drag cancellation, server-clock transition calculation, DST midnight, transition/focus/minute fallback and cleanup, accessible Upcoming group/open behavior, recurrence scope/warning, and URL codec behavior.
- `pnpm build`: passed. Vite reports a non-fatal warning that the single application chunk exceeds 500 kB; code splitting is outside this feature scope.
- Backend integration is not runnable for these features in this worktree because only health handlers currently exist. The frontend therefore follows the frozen handwritten contracts, with the gaps above recorded rather than inventing backend behavior.
