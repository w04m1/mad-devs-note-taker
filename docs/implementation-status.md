# Implementation status

Task 1 is technically complete and release-ready as of 2026-09-10. All 15
release blockers frozen in the [functional audit ledger](development/functional-audit.md)
have been remediated and have deterministic post-remediation evidence. The
ledger remains the authoritative baseline record; this page records the current
implementation state.

## Closed release gates

- **Recovery and activation:** backup creation is fail-closed and atomic;
  restore validates the complete archive and expected schema in a disposable
  database before outage, applies the target in one transaction, and restores
  the prior service state on failure. Compose-compatible target resolution and
  exact Alembic-head checks protect backend, worker, and Beat startup.
- **Recurring lifecycle:** immutable, sealed Trash actions preserve stable
  membership and independent restore units. Superseded and purged records are
  uniformly inaccessible, migration `0004_storage_contract` repairs legacy
  ghosts, and expiry removes authored content and associations while retaining
  only non-public technical tombstones.
- **Background work:** reminder and cleanup invocations drain all eligible work;
  large Trash actions remain atomic. Recipient authorization serializes with
  Settings updates. Persisted failure state uses bounded error codes rather than
  external or authored text.
- **Client intent:** Note and Calendar future-split operations carry a stable
  series version, Upcoming uses one shared pager, and authoring drafts pin their
  timezone and exact unchanged instant.
- **Operations and scale:** Beat health is based on a Beat-owned successful
  publication signal. The exact-10,000 materialization benchmark has explicit
  distribution, row-count, rollback, atomic-visibility, and concurrent-read
  gates.

## Current verification

- Backend lint and safe tests: Ruff passed; 19 tests passed.
- Isolated PostgreSQL/Redis/Celery/Mailpit gate: 34 passed, 19 deselected, with
  migration cycles, legacy repair assertions, sealed-action mutation failures,
  real broker/process coverage, and retained query plans.
- Frontend: 38 tests across 14 files passed; the production build passed.
- Recovery matrix: injected dump, compression, output-write, truncated archive,
  mid-SQL, wrong-target, missing/old/ahead schema, Beat suspension, and Redis-loss
  cases all passed without touching the main Compose project.
- Materialization: three runs per case produced medians of 1.446 seconds with no
  reminder offsets and 9.674 seconds with all three offsets. Every run created
  exactly 10,000 notes, the three-offset case created exactly 30,000 rules and
  30,000 deliveries, rollback residue was zero, and the worst concurrent read was
  1.136 seconds. See the [retained artifact](development/evidence/task1-materialization.json).

## Accepted product and test limits

- SMTP provides at most one application attempt, not exactly-once external
  receipt.
- Recurrence retains its finite 10,000 cap, skipped invalid candidates, and
  earlier-fold rule. Redis Pub/Sub remains non-replaying; HTTP is authoritative.
- The product is local, unauthenticated, single-profile, and has no TLS. It is not
  suitable for public internet exposure.
- Browser E2E is Chromium-only and serial. Performance evidence is host-sensitive.
- Bundle size, accessibility, structured logging, and the ledger's other
  nonblocking findings remain follow-up work; they do not reopen Task 1's release
  gate.
