# Shared contracts

This document freezes the interfaces used by independent workstreams. Additive changes are allowed. Breaking changes require an integration decision-log entry.

## Identity and versions

- Public identifiers are UUID strings.
- Mutable notes, tags, settings, and recurrence series expose a non-null integer `version`.
- JSON mutation requests carry `expected_version`; note mutations in a series also carry `expected_series_version`.
- DELETE requests carry the corresponding expected version as a required query parameter.
- Version mismatch is `409` with `{ "code": "version_conflict", "message": "...", "current": {...} }`.

## Common JSON

Datetimes are offset-qualified ISO 8601 strings. Page responses are `{ "items": [], "total": 0, "page": 1, "page_size": 50 }`. Errors are `{ "code": "...", "message": "...", "field_errors": { ... } | null, "current": {...} | null }`.

`Note` contains `id`, `title`, `body`, `starts_at`, `active`, `tags`, `reminder_offsets_minutes`, `version`, `created_at`, `updated_at`, `deleted_at`, `series_id`, and `recurrence_key`. A tag contains `id`, `name`, `color`, and `version`. Settings contain `email`, `timezone`, and `version`.

## HTTP surface

All REST routes use `/api/v1`.

- `GET/PATCH /settings`
- `GET/POST /notes`
- `GET/PATCH/DELETE /notes/{id}` and `POST /notes/{id}/restore`
- `GET/POST /tags` and `PATCH/DELETE /tags/{id}`
- `POST /series`, `GET /series/{id}`, `POST /series/{id}/split`, `POST /series/{id}/trash`, `POST /series/{id}/restore`
- `GET /calendar`, `GET /upcoming`, `GET /notifications`
- `GET /health/live`, `GET /health/ready`
- WebSocket `/ws`

Note list query parameters include `q`, repeated `tag_id`, `active`, `starts_from`, `starts_to`, `trash`, `sort`, `direction`, `page`, and `page_size`. Text search requires three non-whitespace characters. All selected tags must match. Calendar ranges are half-open and limited to 93 days.

## Note mutations

Create and update accept title, body, offset-qualified `starts_at`, active state, tag UUIDs, and distinct reminder offsets restricted to 10, 60, and 1440 minutes. Updates use full replacement semantics for tag and reminder arrays. Association-only changes increment the note version. Delete is soft deletion. Restore only re-enables reminder deadlines strictly in the future.

## Recurrence

Series creation includes template note fields, `local_start`, IANA `timezone`, `frequency` (`daily`, `weekly`, `monthly`), and inclusive `end_date`. Interval is one and expansion is capped at 10,000 concrete rows. Every occurrence has a stable original `recurrence_key`. Invalid monthly dates and nonexistent DST local times are skipped; an ambiguous time selects the earlier instant. Future splits identify the selected original recurrence key and replace future overrides/cancellations, while preserving earlier rows and history.

## Reminder state machine

Delivery states are `pending`, `claimed`, `attempt_started`, `sent`, `failed`, `unknown`, `missed`, and `cancelled`. The stable identity is `(reminder_rule_id, cycle_number)`. Schedule changes create a cycle; content, tags, active state, and display timezone do not. An unchanged schedule is idempotent. Claims use a token and lease. Eligibility is checked again before the `attempt_started` authorization commit. Default grace is 60 seconds.

## Realtime

Events use `{ "event_id", "type", "occurred_at", "entity_id", "version", "series_id" }`. Types are `note.created`, `note.updated`, `note.deleted`, `note.restored`, `series.updated`, `tag.created`, `tag.updated`, `tag.deleted`, `settings.updated`, `notification.created`, and `resync_required`.

Events invalidate queries. They do not carry authoritative entity state. Clients deduplicate event IDs. Notification toasts additionally deduplicate notification IDs in each tab's `sessionStorage`; notification history must never trigger a toast.

## Environment

The environment contract is the list in section 13 of `PLAN.md`. Local defaults use `demo@example.test`, `Europe/Budapest`, a 1-second reminder scan, 60-second grace, 30-second claim, and a maximum of 10,000 series occurrences.
