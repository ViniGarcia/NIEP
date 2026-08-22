# NIEP Service Socket

NIEP can also run as a local service. In this mode, a daemon keeps the topology
state in memory and the Typer-based `niepctl` sends commands through a Unix
socket.

This is useful for scripts and automation because each command can be executed non-interactively.

## Start The Daemon

From the host machine:

```bash
make vm-daemon
```

This starts the daemon inside the Vagrant VM as root, using `/run/niep.sock` by
default. The socket is created with mode `0600` and then made group-accessible
as `root:niep` with its final mode `0660`. The installer adds its target user to
the `niep` group, so authorized users can run `niepctl` without `sudo`; users
outside the group cannot access the socket. Log out and back in after
installation before using this access for the first time.

To use a different socket:

```bash
make vm-daemon NIEP_SOCKET=/tmp/niep-dev.sock
```

## Send Commands

In another terminal, send commands with `vm-ctl`:

```bash
make vm-ctl NIEPCTL_ARGS="--json status"
make vm-ctl NIEPCTL_ARGS="--json define tutorial/examples/mininet-ping.json"
make vm-ctl NIEPCTL_ARGS="--json topoup"
make vm-ctl NIEPCTL_ARGS="--json mininet pingall"
make vm-ctl NIEPCTL_ARGS="--json topodown"
```

The daemon keeps the loaded topology between calls. For example, `define` and
`topoup` can be sent by separate `niepctl` executions.

## Direct VM Usage

Inside the Vagrant VM, the equivalent commands are:

```bash
cd /home/vagrant/NIEP
sudo .venv/bin/niepd
```

Then, in another VM shell:

```bash
cd /home/vagrant/NIEP
./tools/niepctl --json status
./tools/niepctl --json define tutorial/examples/mininet-ping.json
./tools/niepctl --json topoup
./tools/niepctl --json mininet pingall
./tools/niepctl --json topodown
```

## Shell Completion

The installer exposes `niepctl` in `/usr/local/bin`. Install completion for the
current shell once:

```bash
niepctl --install-completion
```

Restart the shell afterwards. Typer completes command groups and options.
While the daemon is running with an active topology, resource arguments are
queried dynamically:

```text
niepctl container exec <TAB>     # active container IDs
niepctl container shell <TAB>    # active container IDs
niepctl vm management <TAB>      # active VM IDs
niepctl vnf up <TAB>             # active VNF IDs
niepctl sfc down <TAB>           # active SFC IDs
```

For a custom socket, export it so both commands and completion use the same
daemon:

```bash
export NIEP_SOCKET=/tmp/niep-dev.sock
```

Every command has contextual help:

```bash
niepctl --help
niepctl container --help
niepctl container exec --help
```

## Available Commands

Topology commands:

```text
status
define <topology-json>
topoup
topodown
topoclean
topodestroy
```

Mininet commands:

```text
mininet pingall
mininet cmd <node-id> <command...>
```

Container commands:

```text
container list
container exec <container-id> <command...>
container shell <container-id> [shell-command...]
```

VM commands:

```text
vm list
vm management <vm-id>
vm ssh <vm-id> <user> <password>
```

`container exec` is non-interactive and returns a structured exit code and
captured output:

```bash
niepctl \
  container exec doc-alpine ip -o addr show eth0
```

`container shell` upgrades the Unix socket connection to a bidirectional TTY
stream. It defaults to `/bin/sh`:

```bash
niepctl \
  container shell doc-alpine
```

An explicit shell or interactive program can also be selected:

```bash
niepctl \
  container shell doc-alpine /bin/sh
```

The daemon handles one socket client at a time, so an interactive shell keeps
that daemon connection occupied until the shell exits.

VNF commands:

```text
vnf list
vnf management <vnf-id>
vnf up <vnf-id>
vnf down <vnf-id>
vnf action <vnf-id> <action> [args...]
vnf script <vnf-id> <script> [error-script]
```

SFC commands:

```text
sfc list
sfc management <sfc-id>
sfc up <sfc-id>
sfc down <sfc-id>
```

## Smoke Test

Run the socket smoke test:

```bash
make vm-smoke-socket
```

It starts the daemon, loads `tutorial/examples/mininet-ping.json`, runs `topoup`, executes `mininet pingall`, runs `topodown`, and terminates the daemon.
