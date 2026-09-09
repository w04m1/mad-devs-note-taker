# Notetaker implementation plan

## 1. Requirements and agreed decisions

### Requirements extracted from `task.md`

| Area | Required behavior |
|---|---|
| Notes | Title, text, date/time, multiple tags, active/inactive status; create, edit, delete, activate, deactivate, and restore. |
| Tags | Create, rename, delete, and assign a color. |
| Recurrence | Daily, weekly, and monthly series with end dates; edit or delete individual occurrences; change a series from a selected occurrence onward without changing earlier history. |
| Reminders | Multiple offsets per note, including 10 minutes, one hour, and one day; email and in-app notification when due. |
| Eligibility | Inactive and deleted notes do not remind. Reactivation and restoration reinstate only future deadlines. Schedule changes reschedule reminders. |
| Calendar | Month, week, and day views; open notes; drag notes to another date/time. |
| Notes list | Server-side title/body search, tag/status/period filters, sorting by note time and modification time. |
| Upcoming | Today, the current week, and a separate section for past active notes; notes move into the past section without refreshing. |
| Settings | Email address and IANA timezone. Changing timezone changes display, not previously scheduled instants. |
| Realtime | Changes propagate across tabs/devices, including calendar, list, and Upcoming. Notifications appear in every connected tab and do not replay after refresh. |
| Concurrency | Concurrent edits cannot silently overwrite each other. |
| Trash | Soft deletion, restoration, automatic permanent removal after 30 days. |
| Persistence | Notes, tags, and reminder schedules survive server restarts. Downtime policy must be documented. |
| Performance | Several thousand notes must open and paginate responsively; search must cover all matching records. |

### Constraints extracted from `customer-requirements.md`

- Separate frontend and backend communicating over the network.
- React or Vue frontend; Python is an acceptable backend choice.
- Relational persistence, preferably PostgreSQL.
- Authentication is optional.
- Fast, documented local deployment with stated prerequisites.
- External services may be emulated.
- Correct operation with at least two simultaneous clients.
- Reproducible evidence of correctness and an honest account of incomplete work.

The detailed stack, testing tools, seven services, incremental Git history, and decision log come from the additional instructions in this conversation.

### Decisions confirmed during planning

- **Single local profile, no login.** All connected clients share that profile.
- **Finite recurrence:** end date required, maximum 10,000 generated occurrences per series.
- **Future-series edits replace future overrides/cancellations**, with a clear warning.
- **Rescheduling creates a new reminder delivery cycle**, including when an earlier cycle already fired.
- **Missed reminders are skipped**, subject to a short operational grace period.
- **At most one application SMTP attempt per delivery cycle.** Ambiguous SMTP outcomes are not retried.

The repository currently contains the two requirements files and an initialized Git repository with no commits. This phase makes no implementation changes.

## 2. Architecture

Use a modular backend application with shared domain services used by HTTP handlers and Celery tasks.

```text
Browser: React + TypeScript
    │
    ├── HTTP reads/mutations
    └── WebSocket events
             │
       Frontend Vite proxy
             │
           FastAPI
             │
             ├── PostgreSQL
             │     notes, recurrence, reminders,
             │     notifications, transactional outbox
             │
             └── Redis Pub/Sub ── other FastAPI processes

Celery Beat ── Redis broker ── Celery worker
                                  │
                                  ├── PostgreSQL scheduling/claims
                                  ├── Redis event publication
                                  └── SMTP EmailSender ── Mailpit
```

Core rules:

- PostgreSQL is authoritative for application state and scheduled work.
- Redis transports jobs and realtime events; losing Redis data must not lose reminder schedules.
- HTTP owns reads and mutations. WebSockets announce changes and trigger refetching.
- Domain changes, reminder reconciliation, and outbox entries commit together.
- Use ordinary relational transactions and a small transactional outbox, not event sourcing.
- No additional search service, microservices, Kafka, Kubernetes, GraphQL, or global frontend state store.

Use SQLAlchemy 2 typed mappings, an async session per HTTP request, and synchronous sessions in Celery processes. Share transaction-independent domain calculations; keep connection/session setup explicit. Never share sessions across requests, tasks, or worker forks.

## 3. Proposed repository structure

These are proposed relative paths, not files created during planning.

```text
/
├── task.md
├── customer-requirements.md
├── README.md
├── compose.yaml
├── .env.example
├── .gitignore
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── uv.lock
│   ├── alembic.ini
│   ├── migrations/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── api/
│   │   ├── domain/
│   │   │   ├── notes/
│   │   │   ├── recurrence/
│   │   │   └── reminders/
│   │   ├── jobs/
│   │   ├── realtime/
│   │   └── email/
│   └── tests/
│       ├── unit/
│       └── integration/
├── frontend/
│   ├── Dockerfile
│   ├── package.json
│   ├── pnpm-lock.yaml
│   ├── components.json
│   └── src/
│       ├── app/
│       ├── api/
│       ├── components/ui/
│       ├── features/
│       └── realtime/
├── tests/e2e/
├── scripts/
└── docs/
    ├── architecture.md
    ├── contracts.md
    ├── verification.md
    ├── implementation-status.md
    └── development/
```

Pin compatible released dependency versions during bootstrap and commit both lockfiles. Check current documentation through Context7 before library-specific implementation.

## 4. Domain and database model

Use UUID identifiers, UTC-backed `TIMESTAMPTZ` for instants, foreign keys, explicit uniqueness constraints, and non-null integer versions for mutable aggregates.

| Entity | Main fields and purpose |
|---|---|
| `user_settings` | Singleton profile ID, email, IANA timezone, version, timestamps. |
| `notes` | Title, body, `starts_at`, active flag, version, timestamps, `deleted_at`; optional series ID and immutable recurrence key. Stores effective values for ordinary notes and generated occurrences. |
| `tags` | Name, normalized unique name, color, version. |
| `note_tags` | Unique note/tag association. |
| `recurrence_series` | Lineage ID, predecessor ID, local DTSTART, recurrence timezone, normalized RRULE, inclusive end date, split boundary, template fields, version. |
| `series_tags` | Tag associations for the series template. |
| `occurrence_exceptions` | Unique series/recurrence key, overridden fields, cancellation flag. Allows an edited occurrence also to be temporarily cancelled. |
| `reminder_rules` | Stable reminder identity per note, offset, enabled state, current cycle number. |
| `series_reminder_templates` | Reminder offsets used when generating occurrences. |
| `reminder_deliveries` | Reminder identity, cycle number, due instant, state, claim token/expiry, authorization timestamp, result/error metadata. |
| `notifications` | One persistent notification per delivery cycle, scheduled time, creation time, minimal display content. |
| `outbox_events` | Stable event ID, type, entity reference, payload, timestamps, publication state and retry information. |

Important invariants:

- Unique `(series_id, recurrence_key)` for generated occurrences.
- Unique `(reminder_rule_id, cycle_number)` for deliveries.
- Unique notification per delivery cycle.
- Distinct reminder offsets within a note.
- Changes to reminder or tag associations also increment the parent note version.
- Series template changes and occurrence mutations use a shared series concurrency protocol.
- A cancellation marker survives removal of the occurrence’s trashed content, preventing accidental regeneration.
- Search and normal views operate on concrete effective note rows, not virtual recurrence expansion.

Use explicit indexes for:

- Note time and modification-time ordering, with ID tie-breakers.
- Active/deleted state combined with common date queries.
- Tag-to-note lookup.
- Pending deliveries by `due_at`.
- Claim expiry and unpublished outbox events.
- Trash cleanup by `deleted_at`.
- Search text, described below.

## 5. Recurrence model

### Generation

Use `python-dateutil` with an RRULE-style model:

- Frequencies: DAILY, WEEKLY, MONTHLY.
- Interval: one in v1.
- Weekly recurrence uses the start weekday.
- Monthly recurrence uses the start day of month.
- End date is inclusive in the series timezone.
- Require an end date and reject expansion beyond 10,000 occurrences before writing.
- Materialize the entire finite series transactionally, including reminder schedules.

This makes every occurrence immediately available to server-side search, filtering, pagination, and reminders.

Invalid monthly dates are skipped rather than clamped: a series on the 31st does not become a February 28 event. This follows the recurrence behavior documented by [python-dateutil](https://dateutil.readthedocs.io/en/stable/rrule.html).

### Individual occurrence changes

- The occurrence keeps its stable note ID and original recurrence key when moved.
- Its concrete row stores effective edited values.
- Exception metadata records which fields differ from the series.
- Deletion sets `deleted_at`, marks the occurrence cancelled, and cancels pending deliveries.
- Restoration clears cancellation, preserves any earlier override, and restores only future eligible reminders.
- Purging a cancelled occurrence removes its content but keeps the minimal cancellation marker.

### “This and future occurrences”

The request identifies the selected occurrence’s **original recurrence key**, not merely its possibly overridden displayed date.

Within one transaction:

1. Lock and version-check the series and selected occurrence.
2. Validate the new rule and expansion limit.
3. Close the old segment immediately before the selected recurrence key.
4. Create a successor segment in the same lineage.
5. Replace overrides and cancellations in the affected future portion.
6. Reconcile concrete occurrences, reminders, and notifications.
7. Write a single `series.updated` outbox event.

Preserve all earlier occurrence IDs, values, versions, and delivery history.

Where a recurrence slot survives unchanged, retain its note identity and existing delivery cycles. A changed scheduled instant or reminder offset creates a new cycle. New slots receive new identities; removed future slots become internally superseded and disappear from user views. Their delivery history remains available for diagnosis.

The UI explicitly warns that future exceptions will be replaced.

**History protection default:** a series-wide split may not rewrite already-started occurrences. Reject a split whose replacement set contains historical effective occurrences and explain that past notes can still be edited individually. This also covers an occurrence previously dragged into the past.

## 6. Timezone strategy

Keep display timezone separate from recurrence timezone.

- Actual note and reminder instants use `TIMESTAMPTZ`.
- Settings store an IANA identifier.
- Recurrence stores local DTSTART plus its own IANA timezone.
- Reminder offsets are elapsed durations: “one day before” means 24 hours before the occurrence instant.
- Changing profile timezone changes display and date grouping only.
- Existing materialized occurrence and reminder instants are not recalculated on profile changes or routine restarts.

DST defaults:

- Skip nonexistent recurring local times during a spring-forward gap.
- Use the earlier instant for ambiguous recurring times during a fall-back overlap.
- Explicitly validate local candidates with dateutil timezone utilities.
- For manually entered ambiguous times, return the two valid choices and require a selection; reject nonexistent manual times with a field-level error.

HTTP timestamps include an offset. Recurrence creation additionally supplies local start and IANA timezone. Backend validation remains authoritative.

Use Monday as the start of the week. Convert user-local date filters into half-open UTC ranges.

## 7. Durable reminders and email

### Delivery-cycle semantics

A reminder’s logical delivery identity is:

```text
reminder rule ID + cycle number
```

- Creating a reminder creates its first cycle.
- Changing note time creates a new cycle for each reminder.
- Changing one offset creates a new cycle for that reminder.
- Content, tag, or display-timezone changes do not create cycles.
- An unchanged schedule submitted twice does not create extra cycles.
- Activation/restoration resumes eligible undelivered cycles; it does not replay delivered ones.
- A new cycle with a deadline already in the past is marked missed.
- Old deliveries remain immutable audit records.

This implements the selected behavior: a previously reminded note moved into the future may remind again.

### Discovery and claiming

Celery Beat schedules fixed periodic tasks:

| Job | Default interval |
|---|---:|
| Discover due reminders and recover expired claims | 1 second |
| Publish committed outbox events | 1 second |
| Trash cleanup | 1 hour |
| Delivery/outbox maintenance | 1 minute |

Do not create long-lived ETA tasks. Celery documents worker-memory and Redis redelivery caveats for distant-future ETA scheduling. [Celery scheduling guidance](https://docs.celeryq.dev/en/stable/userguide/calling.html)

Due-work flow:

1. A scanner selects eligible due rows in bounded batches using `FOR UPDATE SKIP LOCKED`.
2. It records a claim token and a 30-second lease, then commits.
3. It enqueues short tasks containing delivery ID and claim token.
4. If enqueueing fails or Redis loses the message, the expired lease makes the row discoverable again.
5. Duplicate jobs are safe because workers validate the current token and delivery state.

Start with batches of 100 and a bounded amount of work per scanner invocation.

### Final delivery authorization

Before external email work, the worker:

1. Locks the relevant series, note, and delivery in the documented order.
2. Rechecks the claim token, current cycle, active/deleted state, due time, and grace window.
3. Atomically transitions the delivery to `attempt_started`.
4. Stores the email recipient/content snapshot.
5. Inserts the unique notification and its outbox event.
6. Commits.
7. Calls `EmailSender` once.

Only the worker that successfully performs this transition may call SMTP.

A competing worker or retried task that observes `attempt_started` or a terminal state exits without sending.

After SMTP returns, record `sent` or `failed`. A crash or ambiguous timeout leaves an uncertain outcome, subsequently classified as `unknown`; it is never automatically retried.

The authorization commit is the irreversible boundary. A delete or reschedule committed before it prevents sending. A mutation after it cannot retract the already-authorized email.

### Guarantee and limitation

The selected policy guarantees **at most one application send attempt per cycle**, including Celery retries. It cannot guarantee exactly one received email during arbitrary crashes: SMTP acceptance and a PostgreSQL commit are separate operations. SMTP itself documents duplicate risks around final acceptance timeouts. [RFC 5321, DATA termination](https://www.rfc-editor.org/rfc/rfc5321#section-4.5.3.2.6)

Consequences are explicit:

- Healthy execution produces one email.
- A crash after authorization but before SMTP can lose the email.
- An uncertain SMTP result is retained for inspection rather than retried.
- A stable `Message-ID` helps diagnosis but is not treated as receiver-side deduplication.

### Downtime and eligibility

Use a **60-second grace period**, configurable and documented.

- Normally eligible reminders up to 60 seconds late may run.
- Older pending reminders become `missed`; no email or toast is generated.
- Deactivation/deletion cancels undelivered work immediately.
- Reactivation/restoration reinstates only deadlines strictly after the transaction’s current time, regardless of grace.
- Missing or invalid recipient configuration prevents email delivery and records a visible failure; it does not suppress the in-app notification.
- Redis/backend/worker restarts do not erase schedule rows.

### Email abstraction

```text
EmailSender
├── SMTPEmailSender
└── FakeEmailSender
```

Use configurable SMTP host, port, credentials, TLS, sender address, and timeouts. Mailpit is simply the local SMTP endpoint.

The initial profile uses `demo@example.test`, allowing the default demo to deliver into Mailpit immediately.

## 8. REST API and concurrency

Use `/api/v1`, Pydantic request/response models, generated OpenAPI, and generated TypeScript DTOs.

| Endpoint | Purpose |
|---|---|
| `GET/PATCH /settings` | Email, timezone, version. |
| `GET/POST /notes` | Searchable list and ordinary-note creation. |
| `GET/PATCH /notes/{id}` | Detail and individual updates. |
| `DELETE /notes/{id}` | Versioned soft deletion. |
| `POST /notes/{id}/restore` | Restore an occurrence or ordinary note. |
| `GET/POST /tags` | List/create tags. |
| `PATCH/DELETE /tags/{id}` | Rename/recolor/delete tags. |
| `POST /series` | Create a finite series. |
| `GET /series/{id}` | Series definition and version. |
| `POST /series/{id}/split` | Change this and future occurrences. |
| `POST /series/{id}/trash` | Trash the selected occurrence and following portion. |
| `POST /series/{id}/restore` | Restore an identified trashed portion, subject to retention. |
| `GET /calendar` | Notes in a bounded half-open instant range. |
| `GET /upcoming` | Paginated today/week/past groups and transition metadata. |
| `GET /notifications` | Persistent notification history; never causes toast replay. |
| `GET /health/live`, `/health/ready` | Process and dependency health. |

Series actions identify the selected occurrence and expected series version. Individual recurring-note mutations also carry the expected series version.

Common contracts:

- JSON writes carry `expected_version`; DELETE uses a required version query parameter.
- Series writes carry `expected_series_version`.
- Stale writes return `409 Conflict`.
- Errors use `{code, message, field_errors?, current?}`.
- Datetimes are offset-qualified ISO 8601.
- Page responses use `{items, total, page, page_size}`.
- No automatic retry of non-idempotent POST requests in the client.

### Optimistic locking

Configure SQLAlchemy `version_id_col` on mutable aggregates. Explicitly compare the client’s version with the loaded version; also translate `StaleDataError` into `409`.

SQLAlchemy mapper versioning protects ORM flush operations, so user-facing mutations must not bypass it through unguarded bulk updates. [SQLAlchemy version counters](https://docs.sqlalchemy.org/en/20/orm/versioning.html)

For recurrence changes, serialize mutations through the series row and increment the series version even for individual exceptions. This conservatively makes an outstanding series editor stale after another occurrence changes.

Use a consistent lock order: series, notes ordered by ID, reminder/delivery rows.

Frontend conflict behavior:

- A clean editor may load remote changes.
- A dirty editor retains its draft and original version.
- Realtime updates show “This note changed elsewhere.”
- Saving stale data opens a conflict dialog containing the draft and current server values.
- Offer reload/discard or deliberate manual reapplication.
- Never silently replace the draft’s base version or force an overwrite.

Deleting a tag removes associations, not notes, and invalidates note-derived views. A stale editor submitting a deleted tag receives an explicit validation/conflict response.

## 9. Search, filtering, and pagination

Use PostgreSQL-native search; no dedicated search engine is justified.

For predictable literal search across English and Russian text:

- Search a normalized title/body expression with case-insensitive substring matching.
- Use `pg_trgm` GIN indexes on that expression.
- Escape wildcard characters so user text is treated literally.
- Require at least three non-whitespace characters for text search; return a clear validation message for shorter queries.

This provides direct title/body matching without introducing language-specific stemming assumptions.

Filters:

- All selected tags must match.
- Active, inactive, or either.
- Half-open scheduled-time range.
- Normal notes or trash.
- Sort by scheduled time or modification time, ascending or descending.
- Stable ID tie-breaker.

Choose **indexed numbered pagination**, default 50 and maximum 100. The stated dataset is several thousand notes, and page navigation plus totals fits the list UI. Cursor pagination adds no necessary benefit at this scale.

Calendar requests are bounded to 93 days and return concrete occurrences. Enforce a response-size guard and an actionable “narrow the range” error rather than silently truncating results.

Upcoming groups are mutually exclusive:

- Future active notes remaining today.
- Future active notes after today through the end of the current week.
- Past active notes.

The backend supplies `server_now` and `next_transition_at`.

## 10. WebSockets and notification behavior

Use `/ws` for server events.

Example envelope:

```json
{
  "event_id": "uuid",
  "type": "note.updated",
  "occurred_at": "2026-09-09T12:00:00Z",
  "entity_id": "uuid",
  "version": 4,
  "series_id": null
}
```

Events:

- `note.created`, `note.updated`, `note.deleted`, `note.restored`
- `series.updated`
- `tag.created`, `tag.updated`, `tag.deleted`
- `settings.updated`
- `notification.created`
- `resync_required`

### Publication and recovery

- Save outbox events in the mutation transaction.
- A worker publishes committed events to Redis Pub/Sub.
- Every FastAPI process subscribes and forwards to its own connected sockets.
- Mark an event published only after publication succeeds.
- A crash between publication and acknowledgement may duplicate an event; consumers deduplicate by event ID.
- Refetching authoritative HTTP state makes event ordering noncritical.

Redis Pub/Sub is not a replay log. On socket reconnection, application focus, or Redis subscription recovery, invalidate active queries. Use a 30-second reconciliation refetch while realtime is degraded.

### Toast semantics

Every connected tab handles a live notification independently:

- Use `notification_id` as the toast identity.
- Record the ID in that tab’s `sessionStorage` before displaying.
- Duplicate events and page refreshes do not redisplay it.
- Do not use a global “displayed” flag that allows one tab to suppress another.
- Loading notification history never creates toasts.
- Ignore expired live-toast events older than the reminder grace window.
- Disconnected clients recover notification history without a catch-up toast flood.

Persist history for 30 days. Prune per-tab dedupe entries only after the corresponding live-event window has expired.

Normal-load targets: committed changes visible in another connected client within two seconds; due reminder authorization and notification publication within three seconds. These are engineering targets, not hard realtime guarantees.

## 11. Frontend architecture

Use React, TypeScript, Vite, Tailwind, shadcn/ui, TanStack Query, FullCalendar, React Hook Form, Zod, and pnpm.

Primary screens:

- Calendar
- Notes
- Upcoming
- Trash
- Settings
- Tag management
- Notification history

State ownership:

- TanStack Query: server data, caching, invalidation, refetching.
- React Hook Form: drafts and validation.
- Component state: dialogs and temporary interaction state.
- URL parameters: filters, sorting, pagination, calendar date/view.

Centralize API errors, query keys, and websocket-to-query invalidation. Generate DTOs from OpenAPI; use Zod for form validation rather than maintaining an independent competing API schema.

### Calendar

Use FullCalendar’s React adapter, dayGrid, timeGrid, interaction, and Luxon timezone integration. The small Luxon dependency is justified by actual IANA-zone rendering. [FullCalendar named-zone integration](https://github.com/fullcalendar/fullcalendar-docs/blob/main/_docs-v6/date-library/luxon.md)

- Month dragging preserves local time in the selected display timezone.
- Week/day dragging changes local date/time.
- Recurring drags ask for occurrence or future-series scope.
- Mutation payloads include versions.
- Cancel, failure, or conflict calls FullCalendar’s revert operation and refetches.
- Notes remain point-in-time events; visual blocks do not introduce stored durations or all-day semantics.

### Upcoming and forms

- Schedule a timer for `next_transition_at` and local midnight.
- Refetch on visibility/focus and use a one-minute fallback for browser timer throttling.
- Debounce text search by approximately 300 ms and cancel obsolete requests.
- Preserve dirty form values during query invalidation.
- Use accessible shadcn dialogs, fields, menus, and conflict presentations.
- English UI and plain-text note bodies are the v1 defaults.

## 12. Trash and cleanup

- Delete sets `deleted_at` and cancels pending deliveries transactionally.
- Trash views show individual notes and identifiable recurring deletion groups.
- Restore checks retention and version, reinstates the note, and reconciles future deadlines only.
- Series-portion restore does not overwrite successor-series changes; return a conflict if restoration would overlap an already replaced portion.
- Hourly cleanup permanently removes content deleted at least 30 days ago.
- Purge time is therefore between 30 days and 30 days plus one cleanup interval.
- Lock cleanup candidates so a restore race has a single transactional outcome.
- Publish invalidation events when cleanup changes visible trash state.

Keep minimal recurrence cancellation markers and delivery identifiers where needed for consistency. Remove deleted note text and email snapshots from retained technical records during content purge. Internally superseded future content uses the same 30-day cleanup period.

## 13. Docker Compose and deployment

Run the seven requested long-lived services and one one-shot migration service.

| Service | Dependencies | Health and persistence |
|---|---|---|
| `postgres` | None | `pg_isready`; named data volume. |
| `redis` | None | `redis-cli ping`; AOF volume for operational recovery. |
| `mailpit` | None | Web readiness; local SMTP and inspection UI. |
| `migrate` | Healthy PostgreSQL | Same Python image; `uv run alembic upgrade head`; exits. |
| `backend` | Successful migration | Liveness/readiness endpoints. |
| `worker` | Successful migration, healthy Redis | Celery worker-specific ping. |
| `beat` | Successful migration, healthy Redis | Single instance; scheduler heartbeat. |
| `frontend` | Backend startup | HTTP root check; Vite on `0.0.0.0`. |

Use Compose health conditions and successful-completion dependencies so only one service applies migrations. A failed migration prevents application startup. Compose supports these dependency conditions. [Docker Compose startup order](https://docs.docker.com/compose/how-tos/startup-order/)

Implementation details:

- Shared backend image for backend, worker, Beat, and migrations.
- `uv sync --frozen` and pnpm frozen-lockfile installation.
- Pin runtime/container versions; avoid floating `latest` tags.
- Commit usable local defaults so `docker compose up --build` works without manual secret setup.
- Publish frontend on localhost:5173 and Mailpit UI on localhost:8025.
- Browser requests use relative `/api` and `/ws`.
- Vite proxies internally to `backend:8000`.
- Do not expose PostgreSQL or Redis host ports by default.
- Provide a documented LAN override for testing another physical device; retain the stated unauthenticated-local-app limitation.
- Validate frontend production builds, while the default developer container runs Vite.

Environment contract:

```text
DATABASE_URL
REDIS_URL
CELERY_BROKER_URL
SMTP_HOST
SMTP_PORT
SMTP_FROM
SMTP_USERNAME
SMTP_PASSWORD
SMTP_STARTTLS
SMTP_TIMEOUT_SECONDS
APP_DEFAULT_EMAIL
APP_DEFAULT_TIMEZONE
REMINDER_SCAN_INTERVAL_SECONDS
REMINDER_GRACE_SECONDS
REMINDER_CLAIM_SECONDS
OUTBOX_POLL_INTERVAL_SECONDS
TRASH_CLEANUP_INTERVAL_SECONDS
MAX_SERIES_OCCURRENCES
ALLOWED_ORIGINS
LOG_LEVEL
```

Readiness reports Redis failure as degraded realtime while allowing durable HTTP writes. Runtime reconnect/retry logic remains necessary after startup.

Document prerequisites, startup, tests, migrations, logs, Mailpit, backup/restore, and the difference between volume-preserving shutdown and destructive volume removal.

## 14. Backend testing strategy

Use pytest, pytest-asyncio, HTTPX, and real PostgreSQL. Use injected clocks and `FakeEmailSender` for deterministic behavior. Add a smaller real Celery/Redis/Mailpit integration layer.

| Area | Required evidence |
|---|---|
| CRUD and validation | Notes, tags, relationships, settings, invalid zones, deleted-tag submissions. |
| Recurrence | Daily/weekly/monthly expansion, inclusive end date, 31st-day skipping, expansion limit and atomic rollback. |
| Exceptions | Individual edits/deletes/restores; stable recurrence key; cancellation survives purge/restart. |
| Splits | Earlier history preserved; future exceptions replaced; new and unchanged delivery-cycle behavior; historical replacement rejected. |
| Concurrency | Two independent sessions race updates; one succeeds and one conflicts; association-only edits version correctly. |
| Series races | Individual override versus split, split versus split, deletion versus delivery authorization. |
| Trash | Soft deletion, retention boundary, restore, cleanup/restore race, series restoration conflict. |
| Eligibility | Inactive/deleted notes never authorize new delivery; reactivation/restoration only reinstate future deadlines. |
| Idempotency | Duplicate jobs, competing workers, expired claims, retries, enqueue failure, and Redis message loss. |
| SMTP crash boundaries | Crash before authorization is recoverable; crash after authorization never causes a second SMTP attempt. |
| Rescheduling | Pending cycle cancellation, new cycle after prior delivery, unchanged saves create no extra cycle. |
| Timezones | UTC conversion, DST gap/overlap, elapsed offsets across DST, profile change preserves instants. |
| Search/list | Full-dataset search, tag intersection, status/date/trash filters, stable sorting and pagination. |
| Outbox/realtime | Rollback emits nothing; publication retry duplicates are safe; multiple backend processes receive events. |
| Persistence | Restart backend/worker/Beat/Redis/PostgreSQL with retained volumes; schedules survive and missed policy holds. |

Use test-only job controls and isolated Compose projects. Never expose clock manipulation or database-reset endpoints in the normal application.

## 15. Six Playwright E2E scenarios

1. **Realtime and Upcoming:** two browser contexts; edit in A, observe clean views in B without refresh; verify an imminent active note moves into past.
2. **Notifications:** both contexts receive one toast; Mailpit receives one email; duplicate event and refresh do not replay; persistent history remains available.
3. **Calendar:** drag an event with a profile timezone different from browser timezone; verify backend instant, reload persistence, and month-view time preservation.
4. **Concurrent editing:** both contexts edit the same version; A saves; B retains its draft and receives an explicit conflict on stale save.
5. **Recurrence:** edit one occurrence, cancel another, then split the future portion; verify earlier history and replacement policy.
6. **Trash/restore:** delete and restore a future note across contexts; normal views update and only future reminder deadlines return.

Use real HTTP, WebSockets, PostgreSQL, Redis, worker, and Mailpit. Fixtures may create data through APIs, but each scenario’s key interaction uses the UI. Save traces and screenshots on failure.

## 16. Performance and operational verification

Create a reproducible dataset of at least 10,000 notes/occurrences with realistic tags, text, active states, and trash.

Proposed local targets:

- Warm list/search/calendar API p95 below 300 ms for normal bounded results.
- Ordinary UI updates visible within one second after responses.
- Cross-client propagation within two seconds.
- Reminder authorization/publication within three seconds under normal load.
- Maximum-size finite series creation measured separately, with a target below ten seconds on documented hardware.

Measure and report results rather than introducing hardware-sensitive CI failures.

Inspect query plans for representative searches, filters, and later pages. Avoid loading all notes into Python or the browser to filter them.

Use structured logs with request, event, note, delivery-cycle, and task IDs. Record claim recovery, missed reminders, uncertain SMTP results, outbox lag, and cleanup counts. No additional monitoring service is necessary.

## 17. Workstreams and shared ownership

Freeze these contracts before parallel implementation:

- Entity identities, versions, recurrence keys, and split semantics.
- Reminder cycle/state machine and authorization boundary.
- REST DTOs, errors, filters, and mutation versions.
- WebSocket envelope and event names.
- Transaction ownership and lock ordering.
- Environment variables and Docker build expectations.
- Clock and email interfaces.
- Test fixture ownership and generated-file ownership.

| Workstream | Responsibility and primary ownership | Dependencies and interfaces | Tests and commit milestones |
|---|---|---|---|
| Integration/contracts | Root architecture/contracts, generated DTO coordination, integration | Establishes shared contracts; reviews cross-workstream changes | Contract checks; bootstrap and architecture commits |
| Database/domain foundation | Models, sessions, Alembic revisions | Consumes agreed schema; exposes stable entities | Constraints/migrations; versioned schema commit |
| Backend HTTP/domain | Notes, tags, settings, queries, trash APIs | Models, reminder reconciliation, outbox writer | HTTP/search/OCC/trash tests; focused feature commits |
| Recurrence | Expansion, exceptions, series splitting | Models and transactional reminder interface | Calendar/DST/split/race tests; generation then exception commits |
| Reminders/email | Delivery lifecycle, claims, Celery tasks, SMTP adapters | Note eligibility, recurrence occurrences, outbox writer | Idempotency/crash/reschedule tests; scheduler then email commits |
| Realtime | Outbox publisher, Redis fanout, socket endpoint, client event adapter | Event contracts and committed entity versions | Multi-process fanout/reconnect/dedup tests |
| Frontend | Shell, forms, list, calendar, Upcoming, trash, settings | OpenAPI DTOs, events, conflict contract | Component behavior and feature integration commits |
| Infrastructure/QA/docs | Compose, images, test harness, E2E, performance and final operating docs | Runtime commands and stable vertical slices | Startup/restart/E2E checks; infrastructure and evidence commits |

One owner controls Alembic revisions. Backend and frontend owners control their respective dependency manifests. The integration owner controls shared contract documents and generated DTO publication.

With four active agent slots, combine infrastructure with QA and schedule workstreams in waves rather than attempting all eight simultaneously.

## 18. Dependency graph and implementation order

```text
Repository bootstrap + contracts
                 │
       ┌─────────┼──────────────┐
       ▼         ▼              ▼
Infrastructure  Backend/DB   Frontend foundation
       │         │              │
       │    ┌────┼────────┐     │
       │    ▼    ▼        ▼     │
       │  CRUD Recurrence Outbox/WS
       │    │    │        │     │
       │    └─┬──┘        │     │
       │      ▼           │     │
       │  Reminders/email │     │
       │      │           │     │
       └──────┼───────────┼─────┘
              ▼           ▼
       Integrated feature screens
                    │
                    ▼
      PostgreSQL/Celery integration tests
                    │
                    ▼
       Six E2Es + restart/performance QA
                    │
                    ▼
       Final documentation and verification
```

Recommended waves:

1. Integrator creates initial structure, commits it, then freezes contracts.
2. In parallel: infrastructure, backend/schema foundation, frontend foundation.
3. In parallel: note APIs, recurrence, frontend features against agreed contracts; integrate schema changes through its owner.
4. In parallel: reminders/email, realtime, frontend calendar/Upcoming and conflict handling.
5. Integrate complete vertical slices and E2Es as they become available.
6. Complete restart/failure/performance verification and final documentation.

Recurrence calculations and frontend scaffolding can begin before their backend integration dependencies are finished. Reminder delivery integration waits for stable note/recurrence transactions.

## 19. Git workflow and suggested commit boundaries

During implementation, use isolated `codex/<workstream>` branches/worktrees. Do not have agents change branches in the shared checkout.

Each completed row below results in a real commit after relevant checks. Tests for a feature normally ship in the feature commit; later cross-service tests receive their own commits.

| Milestone | Suggested commit |
|---|---|
| Initial structure, source requirements, ignore rules | `chore: initialize project structure` |
| Agreed contracts and decisions | `docs: define architecture and shared contracts` |
| PostgreSQL, Redis, Mailpit infrastructure | `chore(docker): add local infrastructure services` |
| FastAPI, uv, configuration and health | `chore(backend): bootstrap FastAPI application` |
| React, Vite, pnpm and UI foundation | `chore(frontend): bootstrap React application` |
| Models and initial migrations | `feat(db): add versioned note and recurrence schema` |
| Full application Compose startup gates | `chore(docker): add application services and migration startup` |
| PostgreSQL and E2E harnesses | `test: add integration and browser test harnesses` |
| Note CRUD and settings | `feat(notes): add versioned note CRUD and settings` |
| Tags | `feat(tags): add tag management` |
| Search/filter/pagination | `feat(search): add indexed note queries` |
| Finite recurrence | `feat(recurrence): generate timezone-aware occurrences` |
| Overrides, cancellation and splitting | `feat(recurrence): support exceptions and future series edits` |
| Trash/restore/cleanup | `feat(trash): add restoration and retention cleanup` |
| Durable cycles, discovery and claims | `feat(reminders): add durable reminder scheduling` |
| SMTP and delivery guarantees | `feat(email): add idempotent delivery attempts and Mailpit integration` |
| Outbox and backend WebSockets | `feat(realtime): publish committed changes across processes` |
| List/editor/tags/trash UI | Focused `feat(ui): ...` commits by coherent screen/function |
| Calendar and Upcoming | Separate `feat(calendar): ...` and `feat(upcoming): ...` commits |
| Client realtime and conflicts | Separate synchronization and conflict-handling commits |
| Six cross-service E2Es | `test(e2e): cover multi-client application behavior` |
| Failure/restart evidence | `test(persistence): verify recovery and delivery boundaries` |
| Performance evidence | `test(performance): add representative workload verification` |
| Operating and status documentation | `docs: document setup guarantees and verification results` |

Merge in dependency order while preserving logical commits. Resolve integration problems with subsequent focused commits. Do not manufacture history after implementation or squash the entire project into one commit.

## 20. Development log, risks, and defaults

Each workstream maintains its own file under `docs/development/` to avoid concurrent edits. Entries contain:

- ISO timestamp and milestone.
- Problem or decision.
- Chosen approach and reason.
- Relevant alternative and tradeoff.
- Evidence or related commit.
- Deviations, unresolved problems, or intentionally omitted work.

The integration owner maintains the index and final implementation-status document.

Principal risks:

| Risk | Treatment |
|---|---|
| Exactly-once SMTP receipt cannot be guaranteed | Use the explicitly selected at-most-once attempt policy and test crash boundaries. |
| Series split races and historical preservation | Stable recurrence keys, series versions, lock order, atomic reconciliation, dedicated race tests. |
| DST behavior | Explicit recurrence and manual-entry policies with boundary tests. |
| Lost/duplicate Redis messages | PostgreSQL schedules, leases, outbox retries, consumer deduplication and HTTP resync. |
| Large series transactions | Finite 10,000 limit, prevalidation, bounded expansion and measured performance. |
| Toast suppression across tabs | Per-tab deduplication; no global displayed flag. |
| Unauthenticated local deployment | Single shared profile; local bindings by default; document intended exposure. |
| Dirty editor overwritten by refetch | Preserve drafts and base versions; explicit conflict resolution. |

Remaining defaults are fixed for v1:

- English UI, plain-text notes.
- Monday week start.
- All-selected-tags filtering.
- Three-character minimum literal search.
- Reminder offsets: 10 minutes, one hour, one day.
- Default display timezone: `Europe/Budapest`.
- Notification history: 30 days.
- No production hosting, authentication, rich text, attachments, endless recurrence, or custom recurrence-rule editor.

There are no blocking product questions remaining. Any implementation discovery that changes these decisions must be documented and communicated before altering the agreed behavior.

## 21. Final verification checklist

- [ ] Fresh checkout starts with `docker compose up --build`.
- [ ] Migrations run once and startup fails visibly if they fail.
- [ ] All seven long-lived services become healthy.
- [ ] HTTP and WebSockets work through the frontend origin.
- [ ] Notes, tags, recurrence, reminders, and settings persist through restarts.
- [ ] PostgreSQL integration tests cover the specified behaviors and race conditions.
- [ ] Duplicate Celery execution cannot make a second SMTP attempt for the same cycle.
- [ ] Moving a previously reminded note creates the agreed new delivery cycle.
- [ ] Inactive/deleted notes are suppressed; restoration/reactivation does not backfill elapsed deadlines.
- [ ] Downtime beyond grace marks reminders missed.
- [ ] Recurrence exceptions, splitting, historical preservation, and DST policies pass.
- [ ] Trash permanently removes content after the retention period.
- [ ] Both clients update without refresh and stale editing shows a conflict.
- [ ] Each connected tab receives one live toast without refresh replay.
- [ ] Calendar dragging persists the correct instant.
- [ ] Search covers the full dataset; pagination and representative query plans are verified.
- [ ] All six Playwright scenarios pass with failure artifacts available.
- [ ] Frontend type checking/build and backend quality checks pass.
- [ ] Setup, architecture, guarantees, limitations, and verification commands are documented.
- [ ] Decision logs and incremental Git history reflect the actual development process.
