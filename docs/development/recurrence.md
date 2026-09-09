# Recurrence development log

## 2026-04-02 — backend recurrence and trash wave

### Wall-clock expansion

- Added `python-dateutil` as a locked runtime dependency. Recurrence candidates are generated as naive wall-clock values and validated with `dateutil.tz.datetime_exists` before UTC conversion.
- A nonexistent local candidate is omitted. For an ambiguous candidate, `fold=0` selects the earlier instant. Evidence is in `test_recurrence.py` for the Budapest 2025 gap and overlap.
- Daily and weekly expansion step by one and seven calendar days. Monthly expansion retains the DTSTART day and uses a day-one cursor for months where that day does not exist. This skips invalid dates rather than clamping them.
- `end_date` is compared to each local candidate and is inclusive. Expansion collects the complete result before any ORM writes. The 10,000th occurrence is accepted and the 10,001st raises before persistence.
- `local_start` is authoritative. The shared frontend `NoteWrite.starts_at` field remains required, but the API rejects it unless it equals the first valid generated instant. Ignoring contradictory values was rejected because it would hide client timezone bugs.

### Materialization and contracts

- Added series create/get/split/trash/restore schemas and routes. The split payload follows the frozen frontend names `recurrence_key`, `expected_version`, and `expected_occurrence_version` rather than introducing parallel names from prose.
- Trash/restore accepts an additive optional `recurrence_key`. Omitting it preserves the current frontend whole-series behavior; providing it applies to the selected occurrence and following portion.
- Series creation validates the whole expansion and all tags before materializing concrete notes, tag links, reminder rules/deliveries, templates, and one transactional `series.updated` invalidation event.
- GET returns template data and `occurrence_count` in addition to the minimal frozen response. This is additive and makes the server definition inspectable.

### Concurrency, exceptions, and splits

- Mutations keep the established lock order: series first, notes in UUID order, then reminder rules/deliveries through reconciliation. Individual recurring-note writes require and bump the series version.
- Individual update/delete/restore now upserts exception bookkeeping. `recurrence_key` and note ID remain stable after a move. Overrides contain only effective fields that differ from the template. Delete sets `cancelled`; restore clears cancellation while recalculating the surviving override map.
- A split selects by immutable original recurrence key and separately checks both series and selected note versions. It rejects the whole transaction when any affected effective `starts_at` is historical, including a note dragged into the past.
- The predecessor closes immediately before the boundary and a successor keeps the lineage and points to its predecessor. Future exceptions are removed. Exact surviving UTC slots reuse their note IDs and unchanged reminder cycles; changed/new schedules use normal reconciliation. Earlier rows are untouched.
- Removed split slots use a dedicated internal `superseded_at` marker instead of ordinary trash. This preserves rows and delivery history without exposing them in normal or trash queries. A follow-up migration uses idempotent PostgreSQL DDL because the existing initial migration dynamically imports current metadata. Its revision is `0002_recurrence` rather than bare `0002`, so it does not collide with the independently developed trash-cleanup migration; merging parallel migration heads still requires an Alembic merge revision.

### Portion trash and restore

- Added `series_trashed_at` to distinguish a reversible portion action from an individual cancellation. Portion trash only marks notes that were not already individually deleted, so restore cannot resurrect prior cancellations.
- Restore clears only the portion marker and restores eligible rows. Reminder reconciliation re-enables only deadlines strictly in the future. A portion with any marker older than 30 days is rejected as retention-expired.
- Minimal individual cancellation exceptions are never removed. This keeps cancellation intent available for cleanup/purge work.
- Tag deletion now removes `series_tags` before deleting the tag; leaving the template foreign key was rejected because it made valid tag deletion fail.

### Deviations and limits

- Materialization currently calls the shared reminder reconciler per occurrence. This favors one state-machine implementation and correctness over bulk performance. It is transactionally safe at 10,000 but should be profiled before claiming low-latency maximum-size creation.
- Permanent cleanup job wiring is outside the recurrence module currently present in this branch. The new markers make cleanup semantics possible: superseded rows may be purged only under an explicit history policy, and expired portion content must retain individual cancellation exceptions.
