# Functional audit ledger

## Status and scope

This is an **ongoing audit**, not a closure report or a remediation log. The audited
baseline is exact revision
`defa868561e075afcd35a6b1ddf4af1bd36dd120` (`docs: finalize verification and
decision log index`). The findings below reconcile the requirement reviews,
targeted source reviews, disposable PostgreSQL and Compose checks, and two-browser
walkthroughs recorded in the root Prime Agent session log.

No implementation remediation has begun. No implementation file was changed for
this ledger. Severity is functional and operational severity for this local,
unauthenticated, single-profile application. In particular, the restore finding is
**Critical operational data-loss risk**. It is not a remote-security Critical, and
this audit found no remote-security Critical issue.

The repository-cleanliness note recorded part-way through the audit is now stale.
The owner of `frontend/src/tmp-race-audit.test.tsx` removed that temporary audit
file. Main is clean at the revision above. The leaked isolated Compose project was
also removed. Old, unmounted, main-project-labelled volumes were deliberately not
deleted because their ownership and retained data require an explicit owner
decision.

## Evidence and reproductions

A pass proves only the scope exercised by that command. Historical integrated
results remain historical; the lightweight audit reruns do not turn skipped tests
into PostgreSQL evidence.

### Commands run during this audit

| Command or reproduction | Result and boundary |
|---|---|
| `git status --short --branch` and `git rev-parse HEAD` | Main was clean at `defa868561e075afcd35a6b1ddf4af1bd36dd120` before audit work. A temporary untracked test appeared during the audit and its owner subsequently removed it; main is clean again. A formatter also rewrote `frontend/package.json` during the root gate; inspection followed by `git restore -- frontend/package.json` returned the audited tree to the exact revision. |
| `./scripts/test.sh` | Passed on exact main. It ran 18 safe backend tests and 28 isolated PostgreSQL/real-service tests, migration cycles plus `alembic check`, 30 frontend tests in 12 files, and the production build. The current build transformed 2,086 modules and emitted a 795.00 kB main chunk (240.68 kB gzip), with the expected Vite size warning. |
| `./scripts/compose-config.sh` and `cd backend && uv run --frozen alembic heads` | Compose validation passed; Alembic reported `0003_background (head)`. |
| `cd backend && .venv/bin/pytest -q` | 18 passed, 28 skipped, with two dependency deprecation warnings. The skipped cases need `TEST_DATABASE_URL`; this lightweight run is not PostgreSQL/service evidence. |
| `cd frontend && pnpm test -- --run` | 12 files and 30 tests passed. A temporary audit-only suite separately passed 5/5 before its owner deleted it. |
| `QA_COMPOSE_PROJECT_NAME=<isolated-name> ./scripts/test-postgres.sh tests/integration/test_background_jobs.py tests/integration/test_runtime_services.py` | 9 selected real PostgreSQL/Redis/Celery/Mailpit tests passed in a fresh isolated project. Its containers, volumes, and temporary test file were removed. |
| `sh -c 'set -eu; (echo dump-error >&2; exit 42) | gzip >/tmp/masked.sql.gz; echo status-success'` | Exited 0, printed the success marker, and produced a valid 20-byte empty gzip member. This directly demonstrates the backup pipeline status bug. |
| A failing `gzip -dc /tmp/bad.gz | cat` followed by a success echo | The pipeline exited 0 and reached the success path because POSIX reports the final pipeline member. This directly demonstrates the restore decompression-status bug without touching a database. |
| Disposable PostgreSQL 16.4 databases, migrated through `0003_background`, driven through the frozen backend environment | Confirmed torn Note responses, stale ORM identity after an unlocked preload followed by `FOR UPDATE`, no-op recurring-delete series bumps, the reminder backlog loss, cleanup backlog, exact grace and claim-expiry boundaries, and recovery-token/outbox behavior. Temporary databases, containers, and `/tmp` drivers were removed. |
| `COMPOSE_PROJECT_NAME=notetaker-oracle-01 MAILPIT_UI_PORT=0 docker compose build backend`, then isolated `up -d --wait postgres redis mailpit`, `docker compose run --rm migrate`, and `docker compose run --rm --no-deps ... backend uv run --frozen pytest -c /app/pyproject.toml -vv /tmp/notetaker_oracle_test.py` | 2 passed in 3.47s. This oracle proved English/Russian/literal search, tag intersection, status and half-open filters, stable sort/page behavior, empty out-of-range pages, and Upcoming boundaries/totals across four shared pages. The project was removed with `docker compose down -v`. This closes the earlier backend-list correctness concern; the confirmed Upcoming UI pager defect remains. |
| Isolated exactly-10,000-occurrence materialization matrix | With one cold and three warm requests per case, the zero-offset warm median was **15.740 seconds**. The all-three-offset warm median was **99.940 seconds**, with warm runs from **89.061 to 105.497 seconds**. All eight requests returned 201 with 10,000 occurrences and atomic visibility. |
| Isolated persistence project `nt-persist-1789011146` | Settings, tags, an ordinary note, three reminder rules/nine cycles, and a three-note series with override/cancellation survived sequential PostgreSQL, Redis, backend, worker, and Beat restarts byte-for-byte. A within-grace reminder produced one Mailpit message/notification; a beyond-grace reminder became missed with none. Restart ordering itself consumed about 10–11 seconds while migration ran, which remains relevant to short grace windows. |
| Isolated realtime project `rt-audit-20260310` | After Redis stopped, an existing socket got `resync_required` in 0.186s but stayed open; a late socket got no initial degraded signal; readiness stayed 200; a durable tag mutation was unseen by both sockets for 32.012s. Redis recovery delivered resync and the queued event. The project was removed with volumes. |
| Isolated deployment-negative projects `nt-audit-neg` and `nt-audit-bypass` | A forced migrate exit 42 made initial `docker compose up --wait --wait-timeout 90` fail and kept dependents unstarted. After a later failed migrate, `docker compose restart backend worker beat` still exited 0 and made writers/readiness healthy while `/notes` failed with `UndefinedTableError`; frontend health also masked a proxied API 502. Both projects and volumes were removed. |
| Generated `app.openapi()` consumed with `openapi-typescript 7.13.0` | Generation completed, but the generated page item type was `unknown[]`, confirming the non-authoritative/untyped page contract rather than a tool execution failure. |
| Targeted ASGI/domain probes plus temporary PostgreSQL race tests | Confirmed `q="a b"` is accepted with only two non-space characters; huge page values can produce 500; date-max expansion can fail; configured cap can exceed 10,000; pseudo-zones/weak email pass validation; 100 `ß` characters can expand under casefold and fail; composed/decomposed tag names can coexist; concurrent normalized tag create produced 201 + 500 and rename produced 200 + 500. Temporary resources were removed. |
| Deterministic isolated PostgreSQL/API purge and authorization probes | A fully trashed three-occurrence series was aged 31 days and purged: all Note rows became inaccessible, but the series row retained the exact template title/body, tag and reminder-template associations, and `GET /series/{id}` returned them with count 3. A partial-series control correctly remained readable. A separate database barrier paused authorization after its unlocked Settings read; Settings PATCH committed a new email before authorization committed, yet the later SMTP call used the removed address. Temporary resources were removed. |
| Persisted-error canary probes | Fake SMTP and Redis failures containing recipient, note text, credentials, and tokens were stored verbatim in `ReminderDelivery.error` and `OutboxEvent.last_error`. Purge and maintenance did not scrub them. They were not directly serialized by the current API, but remain exposed to database access, backups, and future diagnostics. Audit rows were removed. |
| `http://127.0.0.1:5173` plus isolated Compose browser stacks, each with two independent Chromium contexts | Confirmed core CRUD/realtime flows, the Settings stale-draft overwrite, stale future-series and Calendar-scope overwrites, duplicate create/admission windows, and recurring-trash representation/restore behavior. Audit-created product rows were cleaned through supported APIs where possible. |
| Fresh isolated `./tests/e2e/run.sh` | All 6 Chromium scenarios passed in 36.3 seconds (81.6 seconds for the complete wrapper). Its containers, network, and volumes were removed. |
| Isolated Beat project `beat-audit-38506`, including `SIGSTOP` and Redis-loss probes | The PID-only health check stayed healthy while the scheduler was stopped for 46.6 seconds and its queue stopped advancing. It also stayed healthy throughout Redis loss while publish attempts blocked or failed. The isolated project and volumes were removed; the main Compose project was not touched. |

During the 10,000-occurrence POSTs, all 4,736 concurrent notes/search probes
returned 200. Their p95 values were 12.18–18.84 ms; the maximum list probe was
401.40 ms and the maximum search probe was 36.97 ms. Probes observed only zero or
10,000 rows, never a partial graph. Stack logs had no error, traceback, exception,
timeout, or deadlock match. Compose/Uvicorn configures no application HTTP request
timeout; the audit client used 600 seconds.

The full materialization artifacts are retained at:

```
/home/w04m1/.prime/agent/session-artifacts/01a08757-0adb-729d-a77e-7f4db1bf55e7/sub-2f3f109d/01a089b7-329b-769a-9f6d-8198b7ee8998/
```

The complete cleanup proof is:

```
/home/w04m1/.prime/agent/session-artifacts/01a08757-0adb-729d-a77e-7f4db1bf55e7/sub-2f3f109d/01a089b7-329b-769a-9f6d-8198b7ee8998/cleanup.txt
```

`REPORT.md` summarizes the method. `results.json` contains exact payloads,
responses, database snapshots, and probe samples. `logs.txt` retains complete
stack logs. `hardware.txt`, `docker_stats.txt`, and the other files retain runtime
context. `cleanup.txt` records final application-row counts of
`0|0|0|0|0|0|0|0|0`, followed by removal of project `audit10k` containers, its two
volumes, and its network. The earlier independent zero-offset/read-baseline
artifacts and teardown proof remain at:

```
/home/w04m1/.prime/agent/session-artifacts/01a08757-0adb-729d-a77e-7f4db1bf55e7/sub-88582517/01a089ac-d812-75cc-ba76-9abaaa121b07/
```

The audit also inspected generated OpenAPI, Compose configuration, Alembic head,
tracked E2E artifacts, and source paths. `tests/e2e/artifacts/results/.last-run.json`
only supports that the last retained run passed. It does not independently prove
scenario count, duration, freshness, or coverage.

### Historical evidence retained from `docs/verification.md`

These results were not all rerun during this audit:

- Final main `./scripts/test.sh`: 18 safe backend tests; 27 isolated
  PostgreSQL/real-service tests with zero skips; migration cycles and `alembic
  check`; 30 frontend tests; and production build.
- `./scripts/test-recovery.sh`: isolated PostgreSQL/Redis restart persistence and a
  happy-path logical dump/replace/load primitive. It bypasses the public
  backup/restore pipelines and therefore does not refute the recovery findings
  below.
- The retained scale run loaded 10,000 notes and recorded calendar 0.087 ms,
  trigram search 17.06 ms, tag filter 6.473 ms, and trash 0.365 ms. These are query
  tripwires, not HTTP/UI p95 claims.
- The isolated Playwright run passed six Chromium scenarios in 40.7 seconds; a
  later fresh-stack rerun passed six in 37.4 seconds. The final recurrence scenario
  passed again in 4.2 seconds after the lineage fix.
- The final focused PostgreSQL/service gate passed 28 selected tests with zero
  skips. `./scripts/smoke.sh` then saw seven healthy long-lived services and a
  completed migration.

## Confirmed defects, grouped by dependency

The ordering below expresses remediation dependencies, not an implementation plan.
“Confirmed” includes reproduced behavior and direct contract/code contradictions.
Some edge-risk items still need a deterministic regression test before their exact
interleaving is considered fully characterized.

### 1. Recovery and schema gates

- **FA-C-RESTORE-ATOMICITY · Critical (operational data loss) — restore is
  neither failure-safe nor
  atomic.** `scripts/restore.sh` uses `gzip -dc | psql`. A truncated archive can
  emit a destructive valid SQL prefix, fail in `gzip`, let `psql` exit 0 at clean
  EOF, restart writers, and print completion. Separately, the `--clean` plain SQL
  dump is restored without `--single-transaction`; a later detected SQL error
  leaves earlier drops/creates committed and leaves application writers stopped.
- **FA-H-BACKUP-INTEGRITY · High — backup can falsely succeed.**
  `scripts/backup.sh` uses `pg_dump | gzip`
  without portable pipeline failure propagation, protected temporary output, or
  post-write validation. A failed/partial dump can be announced as a usable
  backup.
- **FA-H-DB-TARGET · High — `.env` database/user overrides are not the script
  target.** Compose
  interpolates `.env`, but unexported shell expansions in both scripts fall back
  to `notetaker`. The scripts can fail while reporting success, stop services, or
  act on a different default-named database.
- **FA-H-MIGRATION-GATE · High blocker — image transitions and post-restore
  starts can bypass the schema gate.** Compose
  `depends_on: migrate: condition: service_completed_successfully` is creation
  ordering, not an activation gate for a changed application image, and restore
  starts writers directly. Readiness checks only `SELECT 1`; worker/Beat do not
  check Alembic head. Before writers start after an image transition or restore,
  the accepted v1 blocker gate is an exact
  `alembic current --check-heads`-equivalent rather than a new capability
  subsystem.
- **FA-M-SAME-IMAGE-SCHEMA-RECHECK · Medium non-blocker — a routine same-image
  restart does not recheck the Alembic head.** `docker compose restart` does not
  rerun migrate or a head check. This is a resilience/diagnostic gap for an image
  and database already admitted by the activation gate; it is not a release
  blocker and does not require making every routine restart depend on a new
  migration job.

### 2. Recurring Trash persistence and API projection

- **FA-H-TRASH-IDENTITY · High — recurring Trash has no durable
  action/membership identity.** The
  backend stores only mutable `series_trashed_at`, returns 204, and exposes a flat
  note page with no deletion discriminator. Two actions cannot be represented or
  restored independently. A split can reuse trashed rows, overwrite their saved
  content, clear their markers, and destroy the restore unit. Individual restore
  can also make one member visible while leaving the rest trashed and retaining a
  hidden portion marker. These are consequences of one root defect, not separate
  severity headlines.
- **FA-H-PURGE-REDACTION · High — a fully purged series remains
  content-recoverable.** A deterministic
  real PostgreSQL/API reproduction purged every occurrence but retained exact
  `RecurrenceSeries.template_title`/`template_body`, `SeriesTag`, and
  `SeriesReminderTemplate` data. `GET /series/{id}` returned 200 with those values
  and an occurrence count of 3. A partial/live segment is a valid control and must
  retain its template. An expired predecessor must be redacted independently even
  when its successor remains live.

A safe Trash contract needs immutable action identity and membership, grouped
pagination, atomic restore by action ID, and explicit overlap/version/expiry
conflicts. This does not require independent Upcoming pages or new canonical
recurrence mutation routes. Erasure is decided per series segment: after its last
visible or restorable member ages out, remove its user-authored template and
series associations and make normal series reads/mutations return the same 404 as
purged notes, while retaining only non-public technical lineage/collision markers.

### 3. Authoritative database snapshots and concurrency

- **Medium — Note responses can be states that never existed.** Note scalar fields,
  tags, and reminder offsets are read in separate READ COMMITTED statements. A
  barrier reproduction returned old scalar/tag state with a new reminder list.
  List totals can similarly disagree with items. Adding a series token as another
  independent query would worsen this.
- **Medium — recurring mutation can check a stale ORM identity.** The code preloads a
  note unlocked, later selects it `FOR UPDATE` into the same SQLAlchemy identity
  map, and does not force refresh. A two-transaction reproduction showed the
  second load still returning v1 after another transaction committed v2. A
  current token was rejected with stale `current`; a stale token passed the
  explicit check and was caught only by mapper flush, yielding generic 409 with no
  authoritative current resource. No silent write was observed, but the required
  conflict contract fails.
- **Low — repeated recurring DELETE bumps only the series.** The first DELETE
  moved note/series v1 to v2. Repeating DELETE with current tokens returned 204,
  left the note at v2, and moved the series to v3 without a semantic transition or
  matching event.
- **Low — `GET /series/{id}` takes a write lock.** The read route reuses the
  mutation helper's `FOR UPDATE`; SQLAlchemy autobegins and holds the exclusive row
  lock through response assembly and session teardown. It is not a leaked
  transaction, but a read can block series/occurrence writers. Use a plain lookup
  for GET and retain the shared lock protocol only for mutations.
- **Medium — tag races lack stable domain errors.** Normalized create/rename is a
  precheck followed by an insert/update; a uniqueness race can escape as an
  integrity error instead of `409 tag_name_conflict`. Tag deletion after note tag
  validation can turn association insertion into an FK/serialization failure
  instead of explicit invalid-tag/conflict behavior.

### 4. Reminder, outbox, retention, and worker lifecycle

- **FA-H-REMINDER-BACKLOG · High — old reminder rows can make an eligible
  reminder become missed.** With
  101 old pending rows ahead of a row due exactly at `now - 60s`, the first
  100-row scan marked old rows missed but did not reach the cutoff row. One second
  later that row was 61 seconds old and was marked missed without enqueue. A drain
  cannot terminate based only on claim count because a full processed batch can
  contain zero claims.
- **FA-H-CLEANUP-BACKLOG · High blocker — cleanup cannot meet 30 days plus
  one interval when more than 100 rows are eligible.** One hourly call purges one
  batch of 100. With 205 eligible and one recent note, one actual call purged 100
  and left 105 eligible; a 10,000-row portion could take roughly 100 runs.
- **FA-H-RECIPIENT-AUTH · High — reminder authorization can send content to an
  obsolete email.**
  Authorization reads Settings without a lock. A deterministic barrier let PATCH
  commit a replacement email before authorization committed, then the worker sent
  the note content to the removed address. The send cannot be recalled. Recipient
  authorization must serialize with Settings changes in the documented lock
  order; this is a local privacy/integrity defect, not a remote-auth exploit.
- **FA-M-ERROR-SECRETS · Medium — persisted raw failure text can retain
  secrets indefinitely.** SMTP and
  Redis exception strings are copied, merely truncated to 4,000 characters, into
  `ReminderDelivery.error` and `OutboxEvent.last_error`. Canary tests retained
  recipient, note text, credentials, and tokens through purge/maintenance. Replace
  these fields with bounded allowlisted codes/types and scrub legacy values; do
  not persist `str(exc)`, class names, URLs, provider responses, or exception args.
- **Medium — a live SMTP worker can race unknown classification.** A worker commits
  `attempt_started`; maintenance can classify it `unknown` after 60 seconds; the
  same still-live worker can resume and send. Finalization updates only rows still
  in `attempt_started`, so the authoritative DB/UI can remain `unknown` although
  `deliver()` succeeded. The at-most-one application-attempt promise remains
  intact, but the recorded outcome can be false. The agreed correction treats the
  maintenance result as provisional: only the same immutable claim token that was
  already authorized may reconcile `unknown` to the observed `sent` or definitive
  `failed` result. It must not authorize a retry or second SMTP invocation, and
  SMTP remains outside database transactions.
- **Medium — recovery invariants are not database constraints.** The schema permits
  `claimed` with null claim expiry and `attempt_started` with null authorization
  time. Normal code supplies both, but imported/corrupt rows can become
  unrecoverable.
- **Medium operational — enqueue/outbox failures are weakly surfaced.** Enqueue
  errors are swallowed while scan result counts claims rather than successful
  enqueue. Outbox errors retry but lack actionable logging/quarantine; poison rows
  can delay later rows, and the publisher holds DB locks across Redis calls.

The audit positively confirmed lease-token replacement, stale/duplicate-token
rejection, `attempt_started` aging to `unknown`, stable outbox event identity after
transaction rollback, persisted retry backoff, and ordinary retry success. Those
behaviors are not defects.

### 5. Realtime delivery and reconciliation

- **FA-M-REALTIME-RESYNC · Medium — realtime lacks reliable
  degraded/startup resynchronization.** Open
  sockets can remain silently stale during Redis outage; late joiners receive no
  initial degraded signal; startup can accept a socket before subscription; and
  focus/readiness does not force an authoritative refetch of fresh-but-wrong
  caches. Treat one continuously healthy subscriber connection as a live epoch.
  Every connection needs the current availability/epoch state, and loss/recovery
  must move clients into polling/refetch and then a new healthy epoch. History
  refetch after recovery must not replay notification toasts.

Redis Pub/Sub remains an allowed non-replaying transport. `PUBLISH == 0` is still
successful publication because it reports current Redis subscribers, not durable
browser acknowledgement. Only publish exceptions/timeouts retry. The defect is
entry into and recovery from degraded/live epochs, not the absence of replay.

### 6. Settings and frontend optimistic concurrency

- **Medium — first-use Settings initialization races.** Deterministic concurrent
  first GET/GET and GET/PATCH probes both reached the absent singleton before
  insert. One request then escaped as a duplicate-primary-key 500; depending on
  insert order, PATCH can lose to the default row. The minimum backend correction
  is conflict-safe singleton creation followed by reselect-and-lock for PATCH.
- **Medium — dirty Settings can silently overwrite another client.** Two-browser
  proof: both opened v1; A saved v2; B's mounted dirty inputs survived realtime
  refetch but submit read the new prop version 2; B received 200/v3 and replaced
  A's value. This is a real local-profile data-integrity defect.
- **FA-H-FUTURE-SPLIT-STALE-INTENT · High blocker — stale “this and future”
  intent can erase a newer exception.** Both `SeriesForm` and Calendar fetch the
  newest series token only at submit/scope
  confirmation. Two-context proofs showed A opening/dragging under v1, B creating
  an occurrence exception and v2, then A fetching v2 and successfully splitting.
  B's exception/title disappeared. The warning did not authorize changes made
  after A accepted it. This violates the concurrency promise and can silently
  overwrite later-authored future-series state.
- **Medium — same-tick admission and pending/cancel guards are incomplete.** A
  temporary component suite proved two requests can be admitted for note create,
  series create, tag create, Activate, Trash, and Restore, and that Note/Series
  forms can be cancelled while a write is pending. Live simultaneous requests
  produced two distinct notes and two distinct series. Versioned actions generally
  produced one success plus conflict, but can still show apparent cancellation or
  a failed/reverted UI after a successful commit. The minimum confirmed fix scope
  is synchronous frontend in-flight guards; backend idempotency keys are optional
  unless safe retry after an ambiguous transport outcome becomes a promise.
- **Medium — conflict recovery is incomplete.** Several surfaces show only a
  string/raw error and do not offer the required local-vs-current comparison,
  reload-latest, and deliberate manual-reapplication flow. Quick actions also need
  stable displayed tokens and deterministic conflict refetch.
- **Medium — Settings defaults bypass dependency injection, and Upcoming rolls
  their lazy insert back.** `_settings()` calls cached `get_settings()` directly,
  so request/test dependency overrides are not authoritative. `/upcoming` calls
  the same lazy creator outside an owned transaction: it can flush and use a
  default singleton for its response, then roll that insert back at session
  teardown. Inject one defaults source and make initialization conflict-safe and
  durably owned. Lazy initialization itself is allowed in this single-profile
  product; the bypass, rollback, and first-use race are the defects.

### 7. Upcoming, timezones, and browser/server time interpretation

- **FA-H-UPCOMING-PAGINATION · High blocker — Upcoming makes records beyond
  the first 50 unreachable.** The backend intentionally applies one
  `page/page_size` to Today/week/past. The client sends no page value;
  the view renders `.items`, labels `items.length`, and has no shared pager. More
  than 50 records in any group are unreachable. The correction is one shared
  pager sized from the maximum group total. Do not add independent group pages,
  cursors, or sibling Upcoming endpoints.
- **FA-H-TIMEZONE-RACE · High — delayed or changed Settings can alter authored
  instants.** Note and
  Upcoming interactions are enabled before profile settings resolve. A form can
  initialize wall time in the browser/old zone and submit it using a later profile
  zone. Open drafts do not pin the authoring zone. Existing-note save also rebuilds
  an untouched timestamp from minute-resolution wall text, losing seconds and
  fractions and risking overlap-fold changes.
- **Medium — display, filters, and transition timing use inconsistent clocks/zones.**
  Range filters normalize gaps/overlaps silently; Trash/Notifications and early
  renders can use the browser zone; Upcoming schedules from server transition
  data without accounting for cache age.
- **Medium — recurrence gap/overlap UX diverges from the frozen recurrence rule.**
  The backend skips nonexistent generated candidates and chooses the earlier fold
  for recurring ambiguity. The UI rejects a nonexistent anchor rather than showing
  the later first valid occurrence, and it does not require acknowledgement of the
  earlier-fold choice. A later-fold single-occurrence override remains allowed.
- **Medium — backend timezone providers are not reproducible or consistent.** The
  deployed image uses system tzdata for common `ZoneInfo` keys, can fall back to a
  newer Python `tzdata` wheel for missing keys, while `dateutil` does not. The
  wheel-only `America/Coyhaique` was accepted by settings but rejected for
  recurrence. `dateutil.tzfile` also disagrees with `ZoneInfo` after its explicit
  transition table (for example Budapest/New York in 2038), and the native host
  and image carried different tzdb releases. Browser Luxon delegates to host ICU,
  which creates a further unpinned source. This is a concrete provider mismatch,
  not merely an unproved provenance concern.

### 8. Contracts, validation, and generated clients

- **Medium — the promised OpenAPI-to-TypeScript path is absent.** OpenAPI uses an
  untyped page item array, automatic 422 schema despite custom runtime errors,
  undeclared non-2xx responses, incorrect `local_start` format, weak reminder
  offset typing, and unstable generated operation IDs. Frontend DTOs remain
  handwritten and there is no export/generation/drift gate.
- **Medium — frontend field limits narrow the backend contract.** Backend/OpenAPI
  allow note title 255, unbounded body, and tag name 100. The ordinary UI rejects
  title 201–255, body above 10,000, and tag name 81–100; series validation does not
  consistently mirror either side.
- **Medium — tag normalization is underspecified.** Trim+casefold does not define a
  normalized display form and compatibility/canonical uniqueness key, raw length
  is checked before normalization, and no collision-safe migration exists.
- **Medium — email and IANA validation are too permissive.** Email uses a weak
  regex rather than a normalized SMTP-compatible bare-address policy. Timezone
  validation can accept pseudo/implementation keys such as `localtime`/`Factory`;
  defaults are not validated through an equivalent path.
- **Low/Medium — input bounds have holes.** Page has no practical upper cap, and
  search checks trimmed string length rather than at least three non-whitespace
  characters.
- **Medium — recurrence cap/date maximum is not a hard invariant.** Configuration
  can raise the intended 10,000 ceiling, and expansion at `date.max`/year 9999 can
  overflow into a 500 rather than return the last valid item or a defined 422.

### 9. Operations and accessibility

- **FA-H-BEAT-HEALTH · High operational — Beat health is a PID-liveness false
  positive.** The current
  check only tests that a nonempty PID file names an existing process. It stayed
  healthy while the scheduler process was stopped and while Redis publish attempts
  blocked or failed, so it has no finite failure-detection bound for either wedge.
  A Beat-owned local freshness file must advance only from the Beat sending
  process after a successful broker publish; merely checking the process or worker
  execution does not prove scheduler progress. Keep it Beat-container-local so
  backend/worker publication cannot refresh it. A scheduled task executed by a
  worker and a new database heartbeat table would bind health to the wrong
  component and are not required.
- **FA-M-10K-MATERIALIZATION · Medium release blocker absent an owner-approved
  exception — maximum-size synchronous series creation is too slow.** The warm
  median was 15.740 seconds with no offsets and 99.940 seconds with all three
  allowed offsets. All writes were atomic, and concurrent reads remained
  responsive, but the three-offset warm runs took 89.061–105.497 seconds. No
  application timeout is configured, so completion alone is not acceptance.
- **Medium operational — structured application logging is absent.** Application
  code does not provide the PLAN §16 correlation/redaction envelope for request
  failures, reminder recovery/missed/unknown transitions, enqueue/outbox retries
  and lag, cleanup counts, Redis subscriber state/resync, dead WebSocket fanout, or
  Celery task IDs. This does not require replacing third-party logs, tracing, or a
  metrics platform.
- **Medium functional accessibility — focus and result-state management is
  incomplete.** Inline editor focus/return, controlled-dialog return focus,
  removal of focused rows, named filter busy/status regions, settled result-count
  announcements, field error association, and success announcements are missing
  or inconsistent. This is not a remote-security issue; exact WCAG severity should
  remain tied to user-task evidence rather than treated as one blanket Critical.

## Evidence-only gaps

These are missing proof, not automatic functional failures:

1. **High evidence risk:** deterministic two-transaction PostgreSQL tests for
   aggregate Note snapshots, stale ORM identity/membership, note/tag association
   writers, tag delete-versus-write, occurrence edit-versus-split,
   split-versus-split, grouped restore-versus-cleanup, split-versus-restore, and
   same-row Settings writes after initialization. First-use singleton
   initialization is already confirmed rather than an evidence-only gap.
2. **High evidence risk:** the full reminder crash matrix at claim, enqueue,
   authorization, SMTP, and commit boundaries; recurrence/retention authorization
   races; backlog draining; and longer black-box open-socket plus late-join Redis
   outage/recovery cycles. The live-worker classification interleaving itself is
   confirmed rather than an evidence-only gap.
3. **Medium evidence risk:** the audit did prove one product-level
   reminder/restart/grace path in the isolated persistence project. It did not
   exhaust a prolonged-outage matrix across every service order, every reminder
   offset/cycle, ambiguous worker failure, and migration delay relative to the
   short grace window.
4. **Medium evidence risk:** public backup/restore scripts under failed/partial
   dump, empty/corrupt/truncated gzip, mid-SQL failure, `.env`-only custom target,
   prior service state, old/ahead schema, external writers, and post-restore API,
   worker, and Beat health.
5. **Medium evidence risk:** the isolated list oracle closed the main backend
   search/filter/sort/later-page concern, but it does not supply HTTP/UI latency
   percentiles or replace browser proof for every combined control state.
6. **Medium evidence risk:** the audit reproduced open-socket and late-join Redis
   degradation. Longer outage cycles, process-crash timing, cross-browser timezone
   conformance, and the resolved recurrence overlap UX remain unproved.

## Refuted findings and allowed limits

- **Refuted — ordinary-note continuous-open silent overwrite.** Fresh isolated
  two-context runs in both save orders produced 200 then 409. The dirty editor
  retained its DOM identity and original token, and the first write remained in
  HTTP and PostgreSQL. A true simultaneous DB-race test remains an evidence gap;
  it is not proof of an observed silent overwrite.
- **Refuted — recurring single-occurrence editor overwrite.** The second editor
  retained the old note token and received 409 even though it fetched a newer
  series token. This does not refute the distinct future-split defect.
- **Allowed — effective-time recurrence interleaving.** `recurrence_key` is logical
  identity. Overrides and a replacement's effective `starts_at` may cross adjacent
  keys or a split boundary. Do not add global effective-time ordering/uniqueness.
  The earlier proposal to reject any successor effective instant before a
  preserved effective instant is therefore removed.
- **Refuted — split scope follows the displayed/dragged date.** Existing rows are
  selected by immutable original `recurrence_key`, not displayed `starts_at`.
- **Allowed — at-most-one application SMTP attempt.** Exactly-once external email
  receipt across SMTP/DB crash boundaries is impossible. Ambiguous outcomes remain
  `unknown` with no retry. A maintenance-created `unknown` is provisional while
  the same already-authorized token is still live and may be corrected from that
  attempt's eventual observed result; it never grants new send authority.
- **Allowed — product caps and recurrence policy.** Finite series cap at 10,000;
  skipped invalid monthly/DST candidates; earlier fold for recurring ambiguity;
  list/upcoming page max 100; Calendar range max 93 days and explicit 5,000-result
  guard.
- **Allowed — Redis Pub/Sub does not replay.** HTTP remains authoritative and
  refetch-based recovery is the design. Redis `PUBLISH == 0` is successful outbox
  publication: the count is current Redis subscribers, not durable storage or
  browser acknowledgement, and retrying on zero would incorrectly couple outbox
  completion to subscriber presence. Exceptions and timeouts still retry. The
  confirmed problem is incomplete entry into and recovery from degraded/startup
  states.
- **Allowed — purge retains minimal non-public technical facts.** Purge means
  removal of user content plus API irrecoverability, not deletion of every row.
  IDs, lineage/predecessor links, recurrence keys and collision-required effective
  instants, purge/cancellation markers, and bounded delivery/outbox state and times
  may remain when demonstrably required. User-authored/free-form fields,
  associations, snapshots, unsafe error text, and content-bearing exception JSON
  must not. Technical tombstones must not appear in normal APIs, counts, or
  conflict `current` projections. Shared Tag rows remain independent resources;
  purge removes only the purged note/segment associations.
- **Allowed/documented deployment/test limits.** Local unauthenticated
  single-profile/no TLS, Chromium-only serial E2E, host-sensitive performance
  tripwires, and third-party logs remaining native are accepted boundaries.
- **Not a requirement — backend idempotency keys for v1 rapid-click correction.**
  Synchronous frontend admission guards are sufficient for the reproduced
  double-submit. Keys become required only if safe manual retry after an ambiguous
  response is promised.

## Contract decisions

### Binding storage, legacy-data, and activation contract

The storage change is one activation-irreversible Alembic revision named
`0004_storage_contract`. It runs during a planned **full writer outage**: backend,
worker, Beat, migration bypasses, and every other database writer are stopped before
the revision starts and remain stopped until the new application version is ready.
There is no online-expand/contract sequence, action backfill, dual-write period, or
mixed-version writer window.

Existing recurring-Trash state is not guessed into action groups. After `0004`, the
exact legacy-row predicate is:

```sql
note.series_id IS NOT NULL
AND note.deleted_at IS NOT NULL
AND note.series_trashed_at IS NOT NULL
AND note.superseded_at IS NULL
AND note.purged_at IS NULL
AND NOT EXISTS (
  SELECT 1 FROM recurring_trash_action_members member
  WHERE member.note_id = note.id
)
```

Action identity and membership rows remain after restore or expiry, so the
`NOT EXISTS` test stays definitive; a nullable current pointer alone is not legacy
provenance. A row satisfying the predicate is restorable only until its unchanged
`deleted_at + 30 days` deadline. Each match is an independent legacy restore unit,
even when several rows have the same timestamp or series. Restore must target one
legacy note ID, atomically clear that note's `deleted_at` and
`series_trashed_at`, and reconcile only that occurrence's future reminders. It must
not infer or restore a timestamp-, boundary-, or series-wide group. No migration
creates synthetic actions or action members for these rows. Individual restore of
a true action member instead returns stable `409 grouped_restore_required` and the
member can be restored only through atomic restore-by-action.

All new recurring portion-Trash writes use a new immutable trash-action row, immutable
one-row-per-note action membership, and a nullable current-action pointer on each
Note. An action records the commanded series/scope and creation time. Its member
set never changes. The Note pointer is the sole current ownership discriminator;
restoring an action atomically affects only members whose pointer still names that
action, then clears those pointers. Historical action and member rows are retained
as bounded technical facts and are never repurposed. New recurring portion-trash
code does not write `series_trashed_at`; new individual-note trash writes only
`deleted_at`; and legacy restore does not create an action.

A split is rejected atomically with a stable conflict if its affected range crosses
any still-restorable Trash state: either a row matching the legacy predicate above
or a row with a live current-action pointer. It must not reuse, rewrite, clear, or
re-parent those rows. Expired or purged technical tombstones are not restorable;
they remain subject to the separate collision, purge, and lineage rules.

`RecurrenceSeries` gains its own nullable `purged_at`. Once a segment has no visible
or restorable member and retention expires, cleanup redacts its user-authored
fields and associations, sets `purged_at`, and normal reads and mutations return the
same 404 projection as purged notes. The marker is technical retention state, not a
way to expose the redacted series.

`ReminderDelivery` and `OutboxEvent` each gain exactly one persisted `error_code`
field whose values come from a closed, documented allowlist. Migration/activation
maps any needed unresolved legacy failure to a non-sensitive generic legacy code
(or null where no failure state requires a code), scrubs existing raw values, and
drops `ReminderDelivery.error` and `OutboxEvent.last_error`. Neither table gets a
second detail/message/class field. Application code and logs must not persist raw
exception text, arguments, class names, URLs, provider responses, recipient or note
content, credentials, or tokens.

This is an operationally one-way storage contract. Before activation, and only with
proof that no new action/membership write committed, the operator may keep traffic
closed, downgrade `0004`, and reinstall the old release everywhere. Rollback to an
old writer is unsupported once write traffic is activated or the first new action
write commits, whichever occurs first. Recovery after that point means roll forward
or restore a pre-cutover database backup together with its matching old application
and accept loss of later writes; it never means dropping action data or starting old
writers against the activated schema.

### Binding database lock protocol

All code paths that lock more than one mutable domain row must use this global
order: **sorted Tags → Series → Notes → associations/templates → Rules →
Deliveries → Settings → Notifications → Exceptions → Outbox**. Within a class,
lock rows by ascending primary key; Tags are therefore a sorted set, never request
order:

1. **Tags** (sorted)
2. **Series** (`RecurrenceSeries`)
3. **Notes**
4. **associations/templates** (`NoteTag`, `SeriesTag`, and
   `SeriesReminderTemplate`)
5. **Rules** (`ReminderRule`)
6. **Deliveries** (`ReminderDelivery`)
7. **Settings** (`UserSettings`)
8. **Notifications** (`Notification`)
9. **Exceptions** (`OccurrenceException`)
10. **Outbox** (`OutboxEvent`)

Rows that can be changed, deleted, used to authorize a side effect, or used to
validate a mutation take `SELECT ... FOR UPDATE`; do not weaken this to `FOR NO
KEY UPDATE` or take a lock that later needs an upgrade. A stable referenced row
that needs only FK/existence protection may use `FOR KEY SHARE`, still in the same
class order. Lock every already-known row in one ordered statement per class where
practical. Association and template rows are locked after their Tag/Series/Note
parents and before their Rule/Delivery children. A transaction must not acquire a
row from an earlier class after it has acquired a later-class lock. Redis
publication, SMTP, and other network I/O must not run while database row locks are
held. SMTP's existing authorization/attempt
boundary remains a separate at-most-one-attempt protocol, not permission to retry
a send.

After all required locks are held, reselect or explicitly refresh every object
that was loaded before locking, then revalidate expected versions, current
membership, trash/purge visibility, lineage, Settings authorization, and other
preconditions against that locked snapshot. An unlocked preload or ORM identity-map
value is never authoritative. A failed check rolls back the whole transaction and
returns the documented domain `409`/`404`/`422`; it must not partially mutate.
Deadlock or serialization failures may retry the complete database-only operation
from a fresh session with bounded attempts and jitter. Exhaustion returns a stable
conflict/service error. Never retry a transaction after an external side effect
might have happened.

The only protocol exceptions are:

- read-only projections may use one SQL statement or an explicit coherent read
  snapshot without `FOR UPDATE`;
- queue consumers may claim same-class rows with ordered `FOR UPDATE SKIP LOCKED`,
  but after that claim they may acquire only later classes; and
- a row that does not exist cannot be row-locked. Singleton creation and unique
  names therefore use the database uniqueness constraint (or a documented
  transaction-scoped advisory lock), then reselect in the normal order. Expected
  uniqueness/FK races must be translated to a stable domain response or retried;
  they must not escape as a 500.

The lock protocol needs deterministic PostgreSQL regression tests, not
sleep-dependent race tests. Use two independent sessions plus explicit barriers or
test-only hooks to pause after each acquired class. Cover each operation pair that
can touch the same rows, including tag rename/delete versus note or series writes,
note edit versus split, split versus split/restore, grouped restore versus cleanup,
Settings PATCH versus reminder authorization, rule/delivery maintenance, and
notification/exception/outbox creation. Assert the second operation blocks at the
expected class, both runs finish within a statement timeout, and the result is an
authoritative success or stable domain conflict with no deadlock, 500, torn
projection, duplicate side effect, or partial commit. Add a forced
deadlock/serialization test for bounded whole-transaction retry and a forced retry
exhaustion test; assert no SMTP or Redis call is repeated.

The recurrence-authority decision is resolved for local v1: add one
side-effect-free, backend-authoritative preview endpoint that accepts naive
`local_start`, IANA `timezone`, and the recurrence rule, and uses the same pinned
bounded expansion code as mutation. The UI uses the previewed first instant in the
existing required `starts_at` field; create/split still re-expand and validate it
atomically. This is preview-only contract growth. Do not add canonical sibling
create/split/trash/restore routes, a second browser recurrence engine, or a resolver
fingerprint.

The series mutation token name is also resolved. `expected_series_version` is
canonical. Legacy request bodies may continue to accept `expected_version` as a
deprecated v1 alias. If both names are supplied with equal values, accept them; if
they differ, reject atomically with 422. Note mutation token names remain
unchanged. An atomically observed nullable series version on every Note response
remains additive remediation design and must not be assembled by a later,
independent READ COMMITTED query.

Quantitative thresholds remain owner approval work. The 500 ms direct-SQL check
is only a host-sensitive regression tripwire. The measured exactly-10,000 create
path is a **Medium release blocker absent an owner-approved exception**: its warm
median was 15.740 seconds with zero offsets and 99.940 seconds with all three
offsets; the three-offset warm range was 89.061–105.497 seconds. This is not a pass
merely because the application configures no request timeout. Do not claim API/UI
percentiles, cold-start bounds, reminder burst capacity, or an accepted
materialization SLO until the hardware envelope, workloads, sample sizes,
percentiles, and thresholds are approved.

The least-risk first remediation is a create-only fast path. Keep the synchronous
HTTP contract and build the prevalidated ORM graph in bounded chunks. Flush each
chunk without a per-note `SELECT` or per-note reminder reconciliation. Create the
series, notes, templates, rules, deliveries, and outbox record in one database
transaction, so no partial series becomes visible. Preserve the current shared
state-machine paths for edits and splits. An asynchronous create job, with its
additional status, retry, idempotency, cancellation, and UX contract, is a fallback
only if this measured synchronous optimization cannot meet the owner-approved
target.

## Exit condition

The audit remains open. Before calling it closed, reconcile any later specialist
reports into this ledger, apply the resolved concurrency-field compatibility
contract, agree remediation scope and acceptance tests, implement fixes in
dependency order, and rerun the appropriate isolated recovery,
PostgreSQL/service, frontend, browser, scale, and smoke gates. None of that
remediation has begun in this workstream.
