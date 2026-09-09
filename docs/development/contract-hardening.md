# Contract hardening decision log

## 2026-09-09: Read-model response shapes

**Decision.** Keep the backend/OpenAPI shape of `GET /tags` as a bare `Tag[]`. Change every frontend consumer from `data.items` to the array. Tags are a small, complete taxonomy used to populate selectors, so partial tag paging would make note editing incorrect. Changing the backend to a page would also be an unnecessary breaking API change.

**Decision.** Keep `GET /upcoming` paged. Its groups are `today`, `week`, and `past`, and each is a `Page<Note>`. One `page` and `page_size` pair applies to all three groups in v1. Change the frontend from the invented `this_week` unpaged array to the real `week` page. This bounds the past-active group and matches the backend schema.

**Evidence.** `frontend/src/app/live-contract.test.tsx` renders Notes against a tag array and a paged note response. The Upcoming component tests use all three pages. `backend/tests/unit/test_openapi_contract.py` pins the tag-array and Upcoming page references exposed by FastAPI OpenAPI.

## 2026-09-09: Failure containment at the frontend boundary

**Decision.** Add a screen-level React error boundary inside the persistent application shell. An unexpected response that escapes static TypeScript assumptions can replace the current screen with an error and reload action, but it cannot remove navigation. This is containment, not runtime response validation.

**Alternative.** Add Zod decoding to every response in this change. That is wider work and still needs a visible error boundary for render bugs. The current client remains compile-time typed and the focused live-shape regression covers the mismatch that caused the blank Notes page.

**Known limit.** A malformed response is not decoded into a structured `ApiError`; it can still fail during screen rendering. The boundary keeps the shell usable and logs the exception.

## 2026-09-09: Configured recurrence expansion limit

**Decision.** Resolve `Settings` through FastAPI dependency injection in both series create and split handlers. Pass `settings.max_series_occurrences` explicitly into recurrence expansion. Keep 10,000 as the domain helper default for non-HTTP callers.

**Evidence.** A PostgreSQL integration test lowers the setting to two, proves that both a three-row create and replacement split return 422, and proves the failed split leaves the original aggregate unchanged.

## 2026-09-09: Replacement, trash, and history safety

**Decision.** A split from a series-trashed future occurrence is allowed. It follows the frozen rule that future splits replace future cancellations and overrides. Surviving recurrence keys reuse note IDs, clear series trash, and resume eligible pending deliveries without creating a new cycle. A newly introduced slot gets a new ID and cycle 1.

**Decision.** Restoring a series portion only accepts a boundary marked with `series_trashed_at`. An individually cancelled occurrence that overlaps a series-trash range is not marked as series trash and is not revived by the portion restore. A later request using that individual cancellation as the restore boundary returns 404 instead of reporting a successful no-op.

**Decision.** Historical replacement continues to inspect effective `Note.starts_at`, not only the original recurrence key. Thus an otherwise-future occurrence dragged into the past blocks an earlier split with `historical_replacement`.

**Decision.** When replacement changes recurrence keys, removed concrete rows remain as superseded audit rows. They are absent from normal, calendar, and Upcoming reads, and their pending current deliveries are cancelled. New rows are materialized for the new keys. An unchanged surviving slot retains its note identity and delivery cycle.

**Evidence.** PostgreSQL tests cover split over series trash, individual-delete/series-trash restore overlap, a moved historical occurrence, unchanged reminder cycles, and changed-key supersession/cancellation.

## 2026-09-09: Tag deletion is a series mutation

**Decision.** Deleting a tag locks every affected recurrence series before affected notes. It removes both concrete and template associations, updates both aggregates, increments their SQLAlchemy versions, and emits `series.updated` for each affected series in addition to `tag.deleted`.

**Reason.** Without a series version increment, a stale future-series editor could submit a template containing the deleted tag under an unchanged expected version. Concrete notes already versioned through `updated_at`; the series template must use the same concurrency rule.

## 2026-09-09: Manual wall-clock DST policy and narrow deviation

**Decision.** Preserve the backend contract that ordinary note `starts_at` is an offset-qualified instant. A naive datetime is rejected with 422. The browser converts a `datetime-local` value in the profile IANA timezone and rejects a spring-forward gap by wall-clock round-trip. For a fall-back overlap it requires the user to choose one of both valid offset-qualified instants.

**Resolved follow-up.** The manual-entry UI now shows both overlap choices with their UTC offsets and requires an explicit selection. It sends the selected offset-qualified instant. We did not weaken the aware-instant API to accept ambiguous naive values; recurring schedules still use their separate earlier-instant rule.

**Evidence.** The note-form tests cover the Budapest 2026 gap, both overlap choices, the accessible radio group, required selection, and the selected request offset. The PostgreSQL HTTP test rejects a naive manual datetime.

## 2026-09-09: Contract evidence scope

The OpenAPI test pins the high-risk response containers and field names. The frontend regression renders the affected Notes screen against those live JSON shapes. It is not full TypeScript generation from OpenAPI: the generic backend `Page` schema does not encode a concrete item type, and handwritten DTO drift remains possible outside the asserted endpoints.

Verification completed in this worktree:

- Backend Ruff: passed.
- Backend unit tests: 18 passed.
- Full backend suite against PostgreSQL 16: 37 passed.
- Frontend typecheck: passed.
- Frontend Vitest: 12 files, 28 tests passed.
- Frontend production build: passed; Vite reports the existing large-chunk warning.
