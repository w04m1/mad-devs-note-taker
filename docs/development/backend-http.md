# Backend HTTP/domain development decision log

## 2026-04-01: frozen request, response, and error models

**Decision.** Define Pydantic models for settings, tags, notes, pages, Upcoming, and
notifications. All validation failures use the frozen `{code, message, field_errors, current}`
envelope. Datetime bodies and range parameters reject values without a UTC offset. Reminder arrays
accept only 10, 60, and 1440 and both association arrays reject duplicates.

**Alternatives.** Returning FastAPI's default validation detail was rejected because clients need one
stable error shape. `EmailStr` was not added because it rejects the required `example.test` demo
address; a bounded syntax check is used at the domain boundary instead.

**Evidence and deviations.** `docs/contracts.md` fixes these fields and limits. OpenAPI now derives
from the same runtime models. Exact series DTOs remain owned by the recurrence workstream and were
not guessed here.

## 2026-04-01: transaction ownership and optimistic concurrency

**Decision.** Each mutation opens one async SQLAlchemy transaction, locks the aggregate, explicitly
checks `expected_version`, and relies on mapper version columns for the guarded update. Every note
update touches `updated_at`, so tag-only and reminder-only replacements issue a versioned note UPDATE.
Recurring-note mutations first lock and check the series and then lock the note. A global
`StaleDataError` handler is a final race safeguard.

**Alternatives.** Bulk UPDATE statements and version checks outside the write transaction were
rejected because they bypass mapper version behavior or leave a time-of-check race. Incrementing only
association rows was rejected because it would let a stale note editor overwrite association changes.

**Evidence and deviations.** Real PostgreSQL HTTP tests verify an association-only mutation changes
note version. Conflict responses include the current DTO for explicit version mismatches. An
unexpected flush-time `StaleDataError` cannot safely query current state before rollback, so its
fallback conflict has `current: null`.

## 2026-04-01: settings singleton and environment compatibility

**Decision.** Use the reserved UUID `00000000-0000-0000-0000-000000000001` for the local profile and
initialize it transactionally on the first settings request. Validate IANA names with `zoneinfo`.
Accept the frozen `APP_DEFAULT_*` and `REMINDER_SCAN_INTERVAL_SECONDS` names while retaining the
bootstrap aliases.

**Alternatives.** Adding authentication or a user collection was out of scope for the selected
single-profile product. Recomputing stored note instants on timezone updates was rejected by the time
contract.

**Evidence and deviations.** PostgreSQL primary-key uniqueness enforces the singleton identity.
First-read initialization avoids changing the already-shared initial schema migration. A deployment
should call `GET /settings` during initialization; simultaneous first-ever requests can race and one
may receive a database uniqueness error, which is a known narrow bootstrap limitation.

## 2026-04-01: note/tag mutation and reminder reconciliation

**Decision.** Note writes replace tag and reminder arrays. Missing/deleted tag IDs fail explicitly.
Reminder rules keep stable IDs. A start-time change or re-enabling a removed offset creates a new
cycle and cancels pending old work. Content, tags, activation, deletion, and restoration do not create
cycles. Inactive/deleted notes cancel undelivered work; activation/restoration reinstates only a
strictly future deadline. Past new deadlines become `missed`. Entity mutation, delivery changes, note
version, and transactional outbox event flush in one transaction.

**Alternatives.** Recreating all reminder rules on every update was rejected because rule/cycle
identity is durable audit data. Creating new cycles on activation was rejected by the frozen state
machine. Publishing directly to Redis was rejected because a committed database change could lose
its invalidation event.

**Evidence and deviations.** PostgreSQL tests inspect delivery rows and outbox rows after HTTP calls,
including delete/restore and remove/re-add cycles. This wave writes the outbox but does not publish it;
the worker/realtime workstream owns publication.

## 2026-04-01: literal search, filters, ordering, and bounded views

**Decision.** List filtering stays in PostgreSQL. Search escapes backslash, `%`, and `_` before
`ILIKE` against the generated normalized column. Tag filters use GROUP BY/HAVING so every selected tag
must match. Count and page queries cover the full result set. Sorting always adds the UUID tie-breaker.
Page size is capped at 100. Calendar uses a half-open range capped at 93 days and rejects results over
5,000 rather than truncating. DTO assembly batches tags and reminders in two queries per result page.

**Alternatives.** Python-side filtering and per-row association queries were rejected for incomplete
pages and poor scaling. Cursor pagination was rejected because the frozen numbered page contract and
several-thousand-note target do not justify it. Full-text stemming was rejected in favor of predictable
literal English/Russian substrings.

**Evidence and deviations.** Integration tests cover wildcard literals, tag intersection, minimum
search length, stable database paging paths, and the calendar guard. The 5,000 calendar guard is an
additive operational limit because the frozen contract requires a guard but does not set its number.

## 2026-04-01: Upcoming and notification-history reads

**Decision.** Upcoming calculates local midnight and Monday-based week boundaries from the profile
IANA timezone, converts them to UTC, and returns three independent numbered page envelopes plus
`server_now` and the earliest next transition. Notification history is newest-first and read-only; it
has no delivery or toast side effects.

**Alternatives.** Browser-only grouping was rejected because clients could disagree and could not page
the complete dataset. Fixed 24-hour local days were rejected because DST changes alter midnight
boundaries.

**Evidence and deviations.** PostgreSQL HTTP tests cover mutually exclusive past/today grouping. The
frozen contract does not define separate page controls per Upcoming group, so v1 applies one
`page/page_size` pair to all three groups as an additive concrete choice.

## 2026-04-01: PostgreSQL integration-test boundary

**Decision.** Keep HTTP integration tests PostgreSQL-only. They run when `TEST_DATABASE_URL` is set,
with the normal application `DATABASE_URL` pointing to the same already-migrated disposable database.
Each test truncates application tables. The normal suite skips these tests when no explicit test
PostgreSQL is supplied; it never substitutes SQLite or changes PostgreSQL types/index behavior.

**Alternatives.** SQLite and mocked ORM sessions were rejected because they cannot validate
`TIMESTAMPTZ`, computed search columns, PostgreSQL enums, trigram-backed expressions, locking, or real
transactions. Automatically deleting a developer database without an opt-in variable was rejected as
unsafe.

**Evidence and deviations.** The local verification used a disposable PostgreSQL 16 container,
Alembic upgrade `0001`, and all nine tests passed. Redis/Celery/Mailpit behavior is outside this HTTP
wave and needs the background-service integration suite.
