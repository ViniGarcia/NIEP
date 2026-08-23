# Migrating to NIEP 1.2

NIEP `1.2.0a1` is an alpha prerelease built around the installable `niep`
package and the typed application command port. Existing paths remain
available during the `1.2.x` compatibility cycle, but they are deprecated.

## Canonical replacements

| Legacy interface | Canonical interface | Removal policy |
| --- | --- | --- |
| `TOPO-MAN/Command.py` | `niep.application.command` | no earlier than `1.3.0` |
| `TOPO-MAN/Executer.py` | `niep.application.executer` | no earlier than `1.3.0` |
| `TOPO-MAN/InfrastructureRuntime.py` | `niep.runtime.infrastructure` | no earlier than `1.3.0` |
| `TOPO-MAN/Parser.py` | `niep.application.parser` | no earlier than `1.3.0` |
| `TOPO-MAN/Result.py` | `niep.domain.result` | no earlier than `1.3.0` |
| `TOPO-MAN/Service.py` | `niep.application.service` | no earlier than `1.3.0` |
| `TOPO-MAN/SocketServer.py` | `niep.interfaces.socket_server` | no earlier than `1.3.0` |
| `TOPO-MAN/Spec.py` | `niep.domain.spec` | no earlier than `1.3.0` |
| `VEM/ClickOnOSv.py` | `niep.runtime.click_on_osv` | no earlier than `1.3.0` |
| `VEM/Container.py` | `niep.runtime.container` | no earlier than `1.3.0` |
| `VEM/ContainerNetworkRuntime.py` | `niep.runtime.container_network` | no earlier than `1.3.0` |
| `VEM/DockerRuntime.py` | `niep.runtime.docker` | no earlier than `1.3.0` |
| `VEM/LibvirtRuntime.py` | `niep.runtime.libvirt` | no earlier than `1.3.0` |
| `VEM/SFC.py` | `niep.runtime.sfc` | no earlier than `1.3.0` |
| `VEM/TerminalSession.py` | `niep.runtime.terminal_session` | no earlier than `1.3.0` |
| `VEM/VM.py` | `niep.runtime.vm` | no earlier than `1.3.0` |
| `VEM/VMImageStore.py` | `niep.runtime.vm_image_store` | no earlier than `1.3.0` |
| `VEM/VMNetworkRuntime.py` | `niep.runtime.vm_network` | no earlier than `1.3.0` |
| `VEM/VNF.py` | `niep.runtime.vnf` | no earlier than `1.3.0` |
| `CLI/CLI.py` | `python -m niep.interfaces.cli` | no earlier than `1.3.0` |
| `CLI/Launcher.py` | `niep.interfaces.cli` | no earlier than `1.3.0` |
| `CLI/HTTP.py` | `niepctl` and `niepd` | no earlier than `1.3.0` |
| `tools/niepctl.py` | installed `niepctl` | no earlier than `1.3.0` |
| `tools/niepd.py` | installed `niepd` | no earlier than `1.3.0` |
| `tools/niepctl` | installed `niepctl` entry point | no earlier than `1.3.0` |

Every legacy Python path emits a `DeprecationWarning` naming its destination;
the shell launcher prints the equivalent warning on its dependency-fallback
path. Warnings are intentionally not converted to errors by the normal test
suite; consumers should migrate before the first `1.3.0` release candidate.

## CLI migration

Use the installed entry points from any working directory:

```bash
niepd --socket /run/niep.sock
niepctl --json status
niepctl --json define tutorial/examples/mininet-ping.json
```

For the interactive interface, use the package module from the repository root:

```bash
sudo .venv/bin/python -m niep.interfaces.cli
```

The old `CLI/CLI.py` and `tools/*` paths are compatibility launchers only.
Tutorials and Make targets use the canonical commands; the old paths are kept
in this document to make migration explicit.

## Command protocol and results

New integrations should use `CommandRequest` and `CommandResponse` from
`niep.application.commands`. The wire envelope is `niep.command` version `1`.
Requests from older local clients that omit protocol metadata are normalized at
the socket boundary, but new clients should send the complete envelope.

`TopologyService.executor`, `LegacyExecutorAdapter`, numeric parser statuses,
`legacy_status`, `normalize_status`, `PlanningDiagnostic.legacy_code` and
`RuntimeFailure.type`/`id` are
internal compatibility edges, not standalone launchers: they remain owned by
the application boundary for `1.2.x` and are covered by contract tests. New
code should consume typed lifecycle states, `ServiceResult` and typed planner
diagnostics instead of reading legacy fields. `TopologyService.executor` is the
only raw-executor property exposed to old in-process callers and emits the
same `1.3.0` removal warning when read or written.

## Assets and POX

The wheel intentionally excludes VM images, CLI history and the vendored POX
tree. A wheel deployment that needs repository assets must set `NIEP_ROOT` to a
provisioned checkout. The vendored tree is third-party code and follows the
provenance policy in [`pox-provenance.md`](pox-provenance.md).

## Internal compatibility surfaces

These surfaces are deliberately kept behind the application boundary and are
covered by contract tests. They are not additional filesystem shims:

| Surface | Canonical use | Owner and deadline |
| --- | --- | --- |
| `TopologyService.executor` | typed topology ports and lifecycle methods | Application maintainers; warning now, removal no earlier than `1.3.0` |
| `LegacyExecutorAdapter` | `ExecutorTopologyPort` snapshots/operations | Application maintainers; internal-only boundary, review before `1.3.0` |
| `CommandDispatcher` compatibility methods | `CommandRequest`/`CommandRouter` | Interface maintainers; retain for `1.2.x`, review before `1.3.0` |
| `legacy_status` / `normalize_status` | typed result/error boundaries | Runtime maintainers; retain only at adapter edges, review before `1.3.0` |
| `PlanningDiagnostic.legacy_code` | `PlanningDiagnostic.code` | Planner maintainers; retain read-only through `1.2.x`, review before `1.3.0` |
| lifecycle aliases (`OperationStep.status`, `name`, `resource`) | `state`, `operation`, `resource_type` | Lifecycle maintainers; retain through `1.2.x`, review before `1.3.0` |
| runtime error aliases (`RuntimeFailure.type`, `id`) | `resource_type`, `resource_id` | Runtime maintainers; retain through `1.2.x`, review before `1.3.0` |
| legacy numeric parser/executor statuses | typed `ResultCode`, `TopologyState` and diagnostics | Application maintainers; wire compatibility through `1.2.x`, review before `1.3.0` |

`NIEP_DISABLE_LOCAL_POX` is an explicitly owned migration escape hatch for
deployments that provide another controller. The Runtime maintainers own its
semantics; Release maintainers own the decision record. It is not a general
runtime configuration switch. Its use is retained through `1.2.x`, and the
retain/remove decision (with an updated ADR if retained) is due before the
first `1.3.0` release candidate; removal is the default for `1.3.0` unless
that review records a concrete replacement owner.
