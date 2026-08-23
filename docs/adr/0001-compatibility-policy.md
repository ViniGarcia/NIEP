# ADR 0001: Compatibility policy for the 1.2 release

- Status: accepted for `1.2.0a1`
- Date: 2026-08-23

## Context

The package migration introduced 19 old `TOPO-MAN`/`VEM` import paths and
legacy launchers (`CLI/HTTP.py`, four Python launchers and the shell wrapper).
Research scripts may still import those paths, while the canonical package and
command ports are now available. There is no production telemetry proving that
the old paths are unused.

## Decision

Keep the 19 module shims, `CLI/HTTP.py`, four Python launchers and the shell
wrapper through the `1.2.x` line.
Every shim emits `DeprecationWarning`, names its replacement and says that
removal is planned for `1.3.0`. New documentation, Make targets and examples
use `niep`, `niepctl`, `niepd` and `python -m niep.interfaces.cli`.

The compatibility inventory is executable in `tests/test_packaging.py`. Before
removal, the project must review repository references, warning reports from
downstream users when available, and migration-guide coverage. A removal or
extension of the deadline requires a new ADR or an update to this one.

The raw `TopologyService.executor` property follows the same warning and
`1.3.0` removal boundary. `LegacyExecutorAdapter`, `CommandDispatcher`, legacy
numeric statuses, protocol normalization, `PlanningDiagnostic.legacy_code`,
`RuntimeFailure.type`/`id` and lifecycle aliases remain internal compatibility
edges, each owned by its
application/runtime/planner/lifecycle maintainers and covered by contract
tests. They are reviewed before the first `1.3.0` release candidate rather
than removed without consumer evidence. `NIEP_DISABLE_LOCAL_POX` is owned by
Runtime maintainers, with Release maintainers responsible for the decision
record; the retain/remove decision is due before that same `1.3.0` candidate.

## Consequences

The 1.2 release carries a small compatibility cost, but old imports fail with
an actionable warning instead of breaking silently. The canonical API can be
tested independently, and the next major cleanup has an explicit owner and
version boundary.
