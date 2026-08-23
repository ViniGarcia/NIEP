# Local socket security

The NIEP daemon is a privileged local service. It can create and destroy
Mininet, Docker and libvirt resources and can execute commands in their
namespaces. The Unix socket is therefore an authorization boundary, not
merely a convenient file descriptor.

## Threat model and privilege matrix

The protected assets are host networking, Docker containers, libvirt guests,
VNF control channels, topology definitions and the daemon process. The threat
model includes an untrusted local account, a process that can write to a
world-writable directory, and a client that sends malformed or slow input. A
process that already has root-equivalent host capabilities is outside this
boundary.

| Actor / command | Permission | Boundary decision |
| --- | --- | --- |
| root | all topology, VM, container, VNF, SFC and Mininet operations | allowed after valid Linux peer credentials |
| member of the configured `niep` group | the same daemon operations | allowed; membership is intentionally root-equivalent |
| other local UID | no daemon operation | rejected before parsing or dispatch |
| any peer | protocol parsing only | v1 envelope, limits and timeouts apply before dispatch |

On Linux, authentication uses `SO_PEERCRED` for PID/UID/primary GID and
`SO_PEERGROUPS` for supplementary groups. If supplementary groups cannot be
proved by the kernel, only root or the already-proved primary GID can pass;
there is no PID or `/proc` identity fallback. The `niep` group must therefore
be treated like the Docker group: granting membership grants privileged
operations.

## Socket and protocol policy

The default path is `/run/niep.sock`. The daemon creates it as `root:niep`
with mode `0660`. Every parent component must be a root-owned directory, must
not be a symlink, and must not be group/world writable. Before replacing a
stale path, the daemon verifies that it is a socket with the expected owner,
group and mode; an active socket, symlink or regular file is never unlinked.

Requests are newline-delimited JSON v1 (`niep.command`). A non-interactive
client sends one frame, including its newline, and half-closes its write side;
the daemon requires EOF before dispatching. The complete frame is at most
64 KiB. Empty, truncated, duplicate-key,
non-UTF-8, non-finite, nested, unknown-field, wrong-version and extra-frame
requests are rejected before the dispatcher runs. The read timeout is a total
deadline for the header and EOF, not a per-read idle allowance. Request IDs
are bounded and cannot contain control characters. Interactive shell requests
are the documented exception: after the JSON header, the connection remains
open for the bidirectional byte stream.

The default resource limits are deliberately conservative:

| Limit | Default |
| --- | ---: |
| request frame | 64 KiB |
| response frame | 64 KiB |
| read / send timeout | 5 s |
| interactive session timeout | 300 s |
| JSON depth | 16 |
| arguments / argument bytes | 64 / 32 KiB |
| individual argument | 4 KiB |
| interactive sessions | 1 |
| connection workers | 32 |

`container exec`, `container shell` and `mininet cmd` have additional command
argument caps in `SocketLimits`. The limits can be injected by an embedding
daemon or test; the public CLI rejects oversized requests before connecting.

Interactive shells receive one JSON response header and then a private byte
stream. The stream and its worker are closed on normal EOF, bridge failure,
client disconnect or timeout. The daemon continues accepting other clients,
but only the configured number of interactive sessions can hold a stream.

## Audit and troubleshooting

Each request emits a structured audit event with request ID, peer PID/UID/GID,
command, resource identifier, duration and result. It never records the
argument vector, command contents, SSH password, token, traceback or runtime
cause. Public error responses similarly omit internal `detail` and runtime
objects; clients receive a stable generic error when a handler fails.

For an installation, provision the `niep` system group and add only intended
operators to it, then start `niepd` as root. Verify:

```bash
getent group niep
stat -c '%U:%G %a %F' /run/niep.sock
```

Expected output is a `root:niep` socket with mode `660`. If the daemon refuses
to start, inspect each parent directory for ownership, symlinks and writable
bits. If it reports an active socket, stop the existing daemon and retry;
never remove the path manually unless its type and ownership have been
checked. If an operator is rejected, confirm that the process has a fresh
login session with its `niep` supplementary group and that the kernel exposes
Unix peer credentials.

The host tests for this boundary do not require root, Docker, Mininet or
libvirt:

```bash
python -m pytest tests/unit/socket tests/contract/protocol
```
