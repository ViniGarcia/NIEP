# Local command API

The daemon, `niepctl` and the legacy interactive CLI share the versioned
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

## Response envelope

Responses contain `protocol`, `version`, `request_id`, `ok`, `code`,
`message`, and `exit_code`. `data`, `status`, and `detail` are included only
when present. `data` is limited to JSON-shaped values; parser and executor
objects are never returned through this boundary.

`exit_code` is the process-style result for interface adapters. For
`container exec`, it is the container's actual command exit status. Other
successful requests use `0`, and failed requests use `1` unless a more
specific command status applies.

Interactive container shells are an out-of-band stream. The first response
line contains only the JSON response envelope; the stream bytes follow it and
are never placed in `data` or stringified into JSON.

The legacy `CommandDispatcher.dispatch(command, args)` facade remains
available to in-process callers. New callers should use `CommandRequest` and
`CommandResponse` from `niep.application.commands`.

`TopologySession` is the application port for active-topology state. The
`LegacyExecutorAdapter` is the one compatibility boundary that translates
legacy executor fields and methods into the typed topology port. `TopologyService`
uses that port (and keeps only a deprecated raw-executor shim for old in-process
callers); handlers use session operations, snapshots and resource services
without reading legacy fields.
