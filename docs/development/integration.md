# Integration and contracts decision log

## 2026-09-09T18:06:06Z — Repository bootstrap

- **Problem or decision:** Establish an incremental Git baseline before parallel implementation.
- **Chosen approach and reason:** Commit the supplied requirements and plan with only the directory skeleton, ignore rules, and this log. This gives every isolated worktree a common, reviewable starting point.
- **Alternative and tradeoff:** A single large implementation commit would be faster initially but would violate the required auditable workflow and make integration harder.
- **Evidence:** Initial repository commit `chore: initialize project structure`.
- **Deviations or unresolved work:** Runtime code, dependency locks, and deployment files intentionally remain for later focused commits.

## 2026-09-09T18:07:21Z — Freeze shared architecture and contracts

- **Problem or decision:** Parallel backend, frontend, realtime, and infrastructure work needs stable boundaries.
- **Chosen approach and reason:** Freeze UUID/version rules, DTO fields, route names, recurrence identity, reminder states, event envelopes, transaction ownership, and lock ordering in `docs/contracts.md` and `docs/architecture.md`. Additive evolution remains possible; breaking changes require a logged integration decision.
- **Alternative and tradeoff:** Generating contracts only after the backend exists would reduce initial documentation, but it would force frontend and QA work to guess and increase merge conflicts.
- **Evidence:** Contract documentation commit `docs: define architecture and shared contracts`.
- **Deviations or unresolved work:** Exact generated OpenAPI schemas will become authoritative when the backend types land.

## 2026-09-09T18:28:53Z — Resolve backend HTTP configuration integration

- **Problem or decision:** The HTTP branch retained transitional `default_email`/`default_timezone` names while the runtime integration branch had already enforced the frozen `APP_DEFAULT_*` environment contract and removed the aliases.
- **Chosen approach and reason:** Keep only the frozen settings fields and update first-request profile initialization to read `app_default_email` and `app_default_timezone`. This prevents two names for one deployment setting.
- **Alternative and tradeoff:** Retaining compatibility aliases would reduce the merge edit but would allow undocumented environment names to persist and drift.
- **Evidence:** Backend lint and tests after the merge; focused integration commit.
- **Deviations or unresolved work:** The simultaneous first-settings-request race remains documented for a later hardening pass.

## 2026-09-09T18:51:43Z — Linearize recurrence and cleanup migrations

- **Problem or decision:** Recurrence and background branches independently added migrations after `0001`, and their merged note fields produced a duplicate `ix_notes_purged_at` declaration during a fresh schema build.
- **Chosen approach and reason:** Order the lifecycle migrations as `0001 -> 0002_recurrence -> 0003_background`. Keep the explicit table-level purge index and remove the duplicate column-level index flag. This yields one Alembic head and one stable index name.
- **Alternative and tradeoff:** An Alembic merge revision would retain parallel heads, but these branches are being integrated before release and have a natural dependency: cleanup must understand recurrence markers.
- **Evidence:** Fresh-volume `docker compose up --build` migration gate and full backend checks after the focused fix.
- **Deviations or unresolved work:** Revision `0001` still imports mutable ORM metadata; the QA workstream owns replacement with immutable operations.

## 2026-09-09T18:53:13Z — Promote the complete local stack

- **Problem or decision:** Operations documentation still described worker and Beat as unavailable after the background implementation landed.
- **Chosen approach and reason:** Promote `docker compose up --build --wait` as the normal command only after a destructive fresh-volume run proved all images, the three-revision migration chain, seven long-lived health checks, the frontend proxy, and an addressed worker ping.
- **Alternative and tradeoff:** Keeping subset startup instructions would be conservative but false and would hide the now-working reminder processes.
- **Evidence:** Fresh volumes; `migrate` exited 0 at `0003_background`; seven services healthy; proxied readiness returned `{"status":"ok"}`; worker returned `pong`.
- **Deviations or unresolved work:** Deeper failure/restart and cross-process tests remain assigned to the QA workstream.
