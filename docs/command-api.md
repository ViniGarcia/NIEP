# Local command API

The daemon, `niepctl` and the interactive CLI share the versioned
application command port. Its wire protocol is `niep.command` version `1`.

## Request envelope

Requests are JSON objects with these fields:

```json
{
  "protocol": "niep.command",
  "version": 1,
  "request_id": "client-generated-id",
  "command": "status",
  "args": [],
  "options": {}
}
```

`args` contains strings only. Unknown fields, unsupported versions and values
that are not JSON-compatible are rejected before a use case runs. For
compatibility with older local clients, `protocol`, `version`, `request_id`
and `options` may be omitted; the daemon normalizes such a request to v1 and
generates a request ID.

Non-interactive clients half-close the Unix socket write side after the one
newline-terminated request. The daemon waits for EOF before dispatching, so a
second frame is rejected even when it arrives in a later read. Interactive
`container shell` keeps the write side open because bytes after its JSON header
are the terminal stream.

## Response envelope

Responses contain `protocol`, `version`, `request_id`, `ok`, `code`,
`message`, and `exit_code`. `data` and `status` are included only when
present. The socket boundary deliberately omits internal `detail` (and any
other non-whitelisted field); parser and executor objects are never returned
through this boundary.

`exit_code` is the process-style result for interface adapters. For
`container exec`, it is the container's actual command exit status. Other
successful requests use `0`, and failed requests use `1` unless a more
specific command status applies.

Interactive container shells are an out-of-band stream. The first response
line contains only the JSON response envelope; the stream bytes follow it and
are never placed in `data` or stringified into JSON.

The daemon treats this socket as a privileged Linux boundary. It authenticates
`SO_PEERCRED` and (when available) `SO_PEERGROUPS`, requires root or the
explicit `niep` group, bounds frames and interactive sessions, and removes
internal error details from public responses. See
[`socket-security.md`](socket-security.md) for the threat model, limits,
installation and recovery rules.

The legacy `CommandDispatcher.dispatch(command, args)` facade remains
available to in-process callers. New callers should use `CommandRequest` and
`CommandResponse` from `niep.application.commands`.

`TopologySession` is the application port for active-topology state. The
`LegacyExecutorAdapter` is the one compatibility boundary that translates
legacy executor fields and methods into the typed topology port. `TopologyService`
uses that port (and keeps only a deprecated raw-executor shim for old in-process
callers); handlers use session operations, snapshots and resource services
without reading legacy fields.

The old `CLI/CLI.py`, `CLI/Launcher.py`, `CLI/HTTP.py`, `tools/*.py` and the
`tools/niepctl` shell wrapper are retained only for the `1.2.x` compatibility
cycle. They emit a deprecation warning (or the shell equivalent) and are
scheduled for removal no earlier than `1.3.0`; see
[`migration-1.2.md`](migration-1.2.md).

### Resource metrics

`stats` accepts no arguments and returns a `stats` result containing a UTC
`timestamp`, per-instance `resources`, the `daemon` process, and `totals` for
VMs, containers, workloads, and workloads with the daemon. CPU percentages use
100% per core and need two counter samples; an initial or reset running sample
has null CPU. Memory is bytes (VM QEMU RSS, container cgroup usage including
cache, daemon RSS). Totals sum available values and explicitly mark partial
coverage. See the service tutorial for scope and accounting semantics.

`niepctl stats` polls every five seconds by default (`--interval SECONDS`).
`niepctl stats-snapshot` prints one JSON data snapshot; global `--json` retains
the command envelope. `niepctl --json stats` emits JSON Lines while polling.
