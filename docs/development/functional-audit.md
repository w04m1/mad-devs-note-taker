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
| `./scripts/test.sh` | Passed on exact main. It ran 18 safe backend tests, the isolated PostgreSQL/service phase, migration cycles plus `alembic check`, 30 frontend tests in 12 files, and the production build. The current build transformed 2,086 modules and emitted a 795.00 kB main chunk (240.68 kB gzip), with the expected Vite size warning. |
| `./scripts/compose-config.sh` and `cd backend && uv run --frozen alembic heads` | Compose validation passed; Alembic reported `0003_background (head)`. |
| `cd backend && .venv/bin/pytest -q` | 18 passed, 28 skipped, with two dependency deprecation warnings. The skipped cases need `TEST_DATABASE_URL`; this lightweight run is not PostgreSQL/service evidence. |
| `cd frontend && pnpm test -- --run` | 12 files and 30 tests passed. A temporary audit-only suite separately passed 5/5 before its owner deleted it. |
| `QA_COMPOSE_PROJECT_NAME=<isolated-name> ./scripts/test-postgres.sh tests/integration/test_background_jobs.py tests/integration/test_runtime_services.py` | 9 selected real PostgreSQL/Redis/Celery/Mailpit tests passed in a fresh isolated project. Its containers, volumes, and temporary test file were removed. |
| `sh -c 'set -eu; (echo dump-error >&2; exit 42) | gzip >/tmp/masked.sql.gz; echo status-success'` | Exited 0, printed the success marker, and produced a valid 20-byte empty gzip member. This directly demonstrates the backup pipeline status bug. |
| A failing `gzip -dc /tmp/bad.gz | cat` followed by a success echo | The pipeline exited 0 and reached the success path because POSIX reports the final pipeline member. This directly demonstrates the restore decompression-status bug without touching a database. |
| Disposable PostgreSQL 16.4 databases, migrated through `0003_background`, driven through the frozen backend environment | Confirmed torn Note responses, stale ORM identity after an unlocked preload followed by `FOR UPDATE`, no-op recurring-delete series bumps, the reminder backlog loss, cleanup backlog, exact grace and claim-expiry boundaries, and recovery-token/outbox behavior. Temporary databases, containers, and `/tmp` drivers were removed. |
| `COMPOSE_PROJECT_NAME=notetaker-oracle-01 MAILPIT_UI_PORT=0 docker compose build backend`, then isolated `up -d --wait postgres redis mailpit`, `docker compose run --rm migrate`, and `docker compose run --rm --no-deps ... backend uv run --frozen pytest -c /app/pyproject.toml -vv /tmp/notetaker_oracle_test.py` | 2 passed in 3.47s. This oracle proved English/Russian/literal search, tag intersection, status and half-open filters, stable sort/page behavior, empty out-of-range pages, and Upcoming boundaries/totals across four shared pages. The project was removed with `docker compose down -v`. This closes the earlier backend-list correctness concern; the confirmed Upcoming UI pager defect remains. |
| Isolated persistence project `nt-persist-1789011146` | Settings, tags, an ordinary note, three reminder rules/nine cycles, and a three-note series with override/cancellation survived sequential PostgreSQL, Redis, backend, worker, and Beat restarts byte-for-byte. A within-grace reminder produced one Mailpit message/notification; a beyond-grace reminder became missed with none. Restart ordering itself consumed about 10–11 seconds while migration ran, which remains relevant to short grace windows. |
| Isolated realtime project `rt-audit-20260310` | After Redis stopped, an existing socket got `resync_required` in 0.186s but stayed open; a late socket got no initial degraded signal; readiness stayed 200; a durable tag mutation was unseen by both sockets for 32.012s. Redis recovery delivered resync and the queued event. The project was removed with volumes. |
| Isolated deployment-negative projects `nt-audit-neg` and `nt-audit-bypass` | A forced migrate exit 42 made initial `docker compose up --wait --wait-timeout 90` fail and kept dependents unstarted. After a later failed migrate, `docker compose restart backend worker beat` still exited 0 and made writers/readiness healthy while `/notes` failed with `UndefinedTableError`; frontend health also masked a proxied API 502. Both projects and volumes were removed. |
| Generated `app.openapi()` consumed with `openapi-typescript 7.13.0` | Generation completed, but the generated page item type was `unknown[]`, confirming the non-authoritative/untyped page contract rather than a tool execution failure. |
| Targeted ASGI/domain probes plus temporary PostgreSQL race tests | Confirmed `q="a b"` is accepted with only two non-space characters; huge page values can produce 500; date-max expansion can fail; configured cap can exceed 10,000; pseudo-zones/weak email pass validation; 100 `ß` characters can expand under casefold and fail; composed/decomposed tag names can coexist; concurrent normalized tag create produced 201 + 500 and rename produced 200 + 500. Temporary resources were removed. |
| `http://127.0.0.1:5173` plus isolated Compose browser stacks, each with two independent Chromium contexts | Confirmed core CRUD/realtime flows, the Settings stale-draft overwrite, stale future-series and Calendar-scope overwrites, duplicate create/admission windows, and recurring-trash representation/restore behavior. Audit-created product rows were cleaned through supported APIs where possible. |

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

- **Critical (operational data loss) — restore is neither failure-safe nor
  atomic.** `scripts/restore.sh` uses `gzip -dc | psql`. A truncated archive can
  emit a destructive valid SQL prefix, fail in `gzip`, let `psql` exit 0 at clean
  EOF, restart writers, and print completion. Separately, the `--clean` plain SQL
  dump is restored without `--single-transaction`; a later detected SQL error
  leaves earlier drops/creates committed and leaves application writers stopped.
- **High — backup can falsely succeed.** `scripts/backup.sh` uses `pg_dump | gzip`
  without portable pipeline failure propagation, protected temporary output, or
  post-write validation. A failed/partial dump can be announced as a usable
  backup.
- **High — `.env` database/user overrides are not the script target.** Compose
  interpolates `.env`, but unexported shell expansions in both scripts fall back
  to `notetaker`. The scripts can fail while reporting success, stop services, or
  act on a different default-named database.
- **High — migration checks are bypassed on restart and restore.** Compose
  `depends_on: migrate: condition: service_completed_successfully` is creation
  ordering, not a per-start gate. `docker compose restart` does not rerun migrate;
  restore starts writers directly; readiness checks only `SELECT 1`; and
  worker/Beat do not check Alembic head. The accepted v1 gate is an exact
  `alembic current --check-heads`-equivalent before every writer starts, rather
  than a new capability subsystem.

### 2. Recurring Trash persistence and API projection

- **High — a portion deletion has no durable action identity.** The backend stores
  only mutable `series_trashed_at`, returns 204, exposes a flat note page with no
  deletion discriminator, and restores by an open-ended series/boundary range.
  Two actions cannot be represented or restored independently, and pagination
  cannot represent one portion as one item. The UI offers no recurring delete
  scope and always restores one note.
- **High — successor interaction destroys the saved restore unit.** A split can
  reuse trashed future rows, overwrite their saved content, clear trash markers,
  and remove the restorable portion. A later restore reports nothing instead of
  the required explicit successor-overlap conflict.
- **Medium — individual restore leaves hidden inconsistent group state.** The HTTP
  spot check created three occurrences, trashed from occurrence two (204), and
  restored occurrence two through the endpoint used by the UI (200). Occurrence
  two became visible while occurrence three stayed trashed, but the restored row
  retained `series_trashed_at`; a later series restore acted on that hidden marker.
  This proves loss of atomic portion semantics, not permanent data loss.

A safe contract needs immutable trash-action identity and membership, grouped
pagination, restore by action ID, and explicit overlap/version/expiry conflicts.
Exact endpoint/schema design remains remediation work, not a change made here.

### 3. Authoritative database snapshots and concurrency

- **High — Note responses can be states that never existed.** Note scalar fields,
  tags, and reminder offsets are read in separate READ COMMITTED statements. A
  barrier reproduction returned old scalar/tag state with a new reminder list.
  List totals can similarly disagree with items. Adding a series token as another
  independent query would worsen this.
- **High — recurring mutation can check a stale ORM identity.** The code preloads a
  note unlocked, later selects it `FOR UPDATE` into the same SQLAlchemy identity
  map, and does not force refresh. A two-transaction reproduction showed the
  second load still returning v1 after another transaction committed v2. A
  current token was rejected with stale `current`; a stale token passed the
  explicit check and was caught only by mapper flush, yielding generic 409 with no
  authoritative current resource. No silent write was observed, but the required
  conflict contract fails.
- **Medium — repeated recurring DELETE bumps only the series.** The first DELETE
  moved note/series v1 to v2. Repeating DELETE with current tokens returned 204,
  left the note at v2, and moved the series to v3 without a semantic transition or
  matching event.
- **Medium — tag races lack stable domain errors.** Normalized create/rename is a
  precheck followed by an insert/update; a uniqueness race can escape as an
  integrity error instead of `409 tag_name_conflict`. Tag deletion after note tag
  validation can turn association insertion into an FK/serialization failure
  instead of explicit invalid-tag/conflict behavior.

### 4. Reminder, outbox, retention, and worker lifecycle

- **High — old reminder rows can make an eligible reminder become missed.** With
  101 old pending rows ahead of a row due exactly at `now - 60s`, the first
  100-row scan marked old rows missed but did not reach the cutoff row. One second
  later that row was 61 seconds old and was marked missed without enqueue. A drain
  cannot terminate based only on claim count because a full processed batch can
  contain zero claims.
- **Medium — cleanup cannot meet 30 days plus one interval under backlog.** One
  hourly call purges one batch of 100. With 205 eligible and one recent note, one
  actual call purged 100 and left 105 eligible; a 10,000-row portion could take
  roughly 100 runs.
- **Medium — a live SMTP worker can race unknown classification.** A worker commits
  `attempt_started`; maintenance can classify it `unknown` after 60 seconds; the
  same still-live worker can resume and send. Finalization updates only rows still
  in `attempt_started`, so the authoritative DB/UI can remain `unknown` although
  `deliver()` succeeded. The at-most-one application-attempt promise remains
  intact, but the recorded outcome can be false.
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

- **High — open sockets can remain silently stale during Redis outage.** The
  subscriber emits bounded resync signals around failure/recovery while sockets
  remain open. The frontend fallback poll starts on WebSocket close, not on
  degraded state, so mutations during a long Pub/Sub outage can remain unseen.
- **High — startup/late-join race can lose invalidation.** WebSockets can be
  accepted before Redis subscription readiness. Redis `PUBLISH` returning zero
  subscribers is still marked published, and the first client `onopen` skips
  invalidation. A mutation between initial HTTP read and effective subscription
  can therefore remain stale indefinitely.
- **Medium/High — readiness and focus do not close the gap.** `/health/ready`
  reports only PostgreSQL. Global focus handling relies on TanStack staleness, so
  a fresh-but-wrong cache may not refetch. Notification dedupe is count-capped
  rather than expiry-based and does not consistently use canonical
  `notification_id`.

Redis Pub/Sub itself remains an allowed non-replaying transport. The defect is the
missing reliable degraded/startup resynchronization, not the lack of replay.

### 6. Frontend optimistic concurrency and mutation admission

- **High — dirty Settings can silently overwrite another client.** Two-browser
  proof: both opened v1; A saved v2; B's mounted dirty inputs survived realtime
  refetch but submit read the new prop version 2; B received 200/v3 and replaced
  A's value. This is a real local-profile data-integrity defect.
- **Medium — stale “this and future” intent can erase a newer exception.** Both
  `SeriesForm` and Calendar fetch the newest series token only at submit/scope
  confirmation. Two-context proofs showed A opening/dragging under v1, B creating
  an occurrence exception and v2, then A fetching v2 and successfully splitting.
  B's exception/title disappeared. The warning did not authorize changes made
  after A accepted it. Severity is bounded because this operation explicitly
  replaces future exceptions, but the concurrency promise is still broken.
- **High — same-tick admission and pending/cancel guards are incomplete.** A
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

### 7. Upcoming, timezones, and browser/server time interpretation

- **High — Upcoming exposes only the first shared page.** The backend intentionally
  applies one `page/page_size` to Today/week/past. The client sends no page value;
  the view renders `.items`, labels `items.length`, and has no shared pager. More
  than 50 records in any group are unreachable. The correction is one shared
  pager; independent per-group cursors are not required.
- **High — delayed or changed Settings can alter authored instants.** Note and
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

- **Medium operational — structured application logging is absent.** Application
  code does not provide the PLAN §16 correlation/redaction envelope for request
  failures, reminder recovery/missed/unknown transitions, enqueue/outbox retries
  and lag, cleanup counts, Redis subscriber state/resync, dead WebSocket fanout, or
  Celery task IDs. This does not require replacing third-party logs, tracing, or a
  metrics platform.
- **Medium/High functional accessibility — focus and result-state management is
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
   split-versus-split, settings initialization/write, grouped restore-versus-cleanup,
   and split-versus-restore.
2. **High evidence risk:** the full reminder crash matrix at claim, enqueue,
   authorization, SMTP, and commit boundaries; recurrence/retention authorization
   races; backlog draining; live-worker classification; and black-box open-socket
   plus late-join Redis outage/recovery.
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
7. **Low evidence risk:** exact 10,000-occurrence materialization latency, hardware
   percentiles, and browser/UI p95 responsiveness.

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
  `unknown` with no retry.
- **Allowed — product caps and recurrence policy.** Finite series cap at 10,000;
  skipped invalid monthly/DST candidates; earlier fold for recurring ambiguity;
  list/upcoming page max 100; Calendar range max 93 days and explicit 5,000-result
  guard.
- **Allowed — Redis Pub/Sub does not replay.** HTTP remains authoritative and
  refetch-based recovery is the design. The confirmed problem is incomplete entry
  into and recovery from degraded/startup states.
- **Allowed/documented deployment/test limits.** Local unauthenticated
  single-profile/no TLS, Chromium-only serial E2E, host-sensitive performance
  tripwires, and third-party logs remaining native are accepted boundaries.
- **Not a requirement — backend idempotency keys for v1 rapid-click correction.**
  Synchronous frontend admission guards are sufficient for the reproduced
  double-submit. Keys become required only if safe manual retry after an ambiguous
  response is promised.

## Unresolved contract decision

One material interface decision remains unresolved. `docs/contracts.md` says that
series mutations carry `expected_series_version`, while split/trash/restore
currently accept `expected_version`. Choose one of these before remediation:

1. preserve the frozen external name `expected_series_version` and migrate the
   backend and frontend; or
2. formally amend the frozen contract to `expected_version` and record the
   compatibility/breaking-change decision.

This ledger does not select either option. A separate additive proposal to expose
an atomically observed nullable series version on every Note representation is
also remediation design work; its exact public field name should be reconciled
with the decision above.

## Exit condition

The audit remains open. Before calling it closed, reconcile any later specialist
reports into this ledger, resolve the concurrency-field name, agree remediation
scope and acceptance tests, implement fixes in dependency order, and rerun the
appropriate isolated recovery, PostgreSQL/service, frontend, browser, scale, and
smoke gates. None of that remediation has begun in this workstream.
