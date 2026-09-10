# Recurrence lineage tip enforcement

## Problem

A series split locked only the requested series and then scoped affected notes to that series. After `A` was split into `A -> B`, a later request could split the closed `A` again. That produced a second active successor of `A`. The note collision query did not prevent every case because it only compared generated instants with preserved keys and effective start times before the selected boundary. A backward-shift collision could be caught, but that check was not a lineage-shape invariant.

The required invariant is one linear successor chain. Only the current open lineage tip may be split. A series is not an open tip when either:

- `split_boundary` is non-null, which records that this segment was closed by a successful split; or
- a row exists whose `predecessor_id` is the requested series, which defensively detects an already-created successor even if legacy or inconsistent data lacks `split_boundary`.

A leaf may have its own `predecessor_id`. That means it follows another segment; it does not make the leaf closed.

## Implementation decisions

1. The split transaction first locks the requested `recurrence_series` row, as before. It then checks the two tip conditions before selecting or mutating notes.
2. A closed or non-leaf target returns HTTP 409 with code `series_not_leaf`, message `Only the open leaf recurrence series can be split`, and current `id`, `split_boundary`, and `successor_id` evidence.
3. The leaf check precedes the expected-version check. A retry of a completed split therefore reports the stable structural reason instead of sometimes returning `version_conflict`. Open leaves still use the existing optimistic version check.
4. The lock order remains series row, then occurrence rows. No future lineage rows are locked because a rejected predecessor split does not reconcile them. Two legitimate splits of the same tip serialize on the same predecessor row. After the first commits, the second statement observes the closed row and rejects it.
5. The existing collision logic remains. It still protects preserved earlier segments when a valid leaf split moves a generated schedule backward.

## Alternatives considered

### Reconcile every active future segment

This would require locking all lineage series and note rows, deciding how to rewrite multiple segment templates and exceptions, and defining a stable global lock order. It is much broader than the product's split-one-tip operation and has greater deadlock and history-corruption risk. It was rejected.

### Check only `split_boundary`

This is sufficient for rows produced by the current transaction, but it does not detect a pre-existing successor if old or manually repaired data has a missing boundary. The explicit successor lookup is cheap and provides defensive evidence in the 409 response.

### Check only for a successor row

This misses a closed row whose successor was removed or whose data is partially inconsistent. It also ignores the authoritative closure marker. Both signals are checked.

### Reject every row with `predecessor_id`

This would reject valid `B -> C` splits because `B.predecessor_id = A.id`. It confuses "has a predecessor" with "has a successor" and was rejected.

### Add a unique database constraint on `predecessor_id`

A partial or ordinary unique constraint for non-null predecessor IDs would be useful defense in depth. It is not needed for correctness on the application path because every split locks the predecessor before it can create a successor. Adding it would also require an idempotent migration and a policy for any existing duplicate lineage data. This focused fix keeps schema unchanged. The defensive successor query exposes inconsistent data instead of adding migration-time cleanup semantics.

### Depend on collision detection

Collision detection deals with time slots, not graph shape. Parallel successors may have non-overlapping schedules, so no collision query can enforce a linear lineage. It remains a separate validation after the tip invariant.

## PostgreSQL evidence

The integration coverage uses the real PostgreSQL suite and verifies:

- `A -> B`, followed by the same split request against `A`, returns `409 series_not_leaf` and identifies `B`;
- the rejected retry is atomic: lineage row count, visible active-note count, and duplicate active recurrence-key count do not change;
- the active recurrence keys contain no duplicates after the rejected retry;
- splitting the leaf `B` succeeds and creates `B -> C`, proving that a non-null `predecessor_id` alone is allowed;
- the existing backward-shift test for a `B` split colliding with a preserved `A` occurrence returns `409 recurrence_collision`, leaves the lineage at two rows, and leaves the leaf version and boundary unchanged.

Verification commands and their final results are recorded in the commit/report for this branch. Ruff is run against all backend application and test code. The non-PostgreSQL unit selection is run separately. `scripts/test-postgres.sh` runs migration upgrade/check/downgrade cycles and the full PostgreSQL/runtime/Celery-marked suite with `FAIL_ON_SKIP=1`.
