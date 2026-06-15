# NIEP Service Socket

NIEP can also run as a local service. In this mode, a daemon keeps the topology state in memory and `niepctl.py` sends commands to it through a Unix socket.

This is useful for scripts and automation because each command can be executed non-interactively.

## Start The Daemon

From the host machine:

```bash
make vm-daemon
```

This starts the daemon inside the Vagrant VM as root, using `/tmp/niep.sock` by default.

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

The daemon keeps the loaded topology between calls. For example, `define` and `topoup` can be sent by separate `niepctl.py` executions.

## Direct VM Usage

Inside the Vagrant VM, the equivalent commands are:

```bash
cd /home/vagrant/NIEP
sudo python3 tools/niepd.py --socket /tmp/niep.sock
```

Then, in another VM shell:

```bash
cd /home/vagrant/NIEP
python3 tools/niepctl.py --socket /tmp/niep.sock --json status
python3 tools/niepctl.py --socket /tmp/niep.sock --json define tutorial/examples/mininet-ping.json
python3 tools/niepctl.py --socket /tmp/niep.sock --json topoup
python3 tools/niepctl.py --socket /tmp/niep.sock --json mininet pingall
python3 tools/niepctl.py --socket /tmp/niep.sock --json topodown
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
```

VM commands:

```text
vm list
vm management <vm-id>
vm ssh <vm-id> <user> <password>
```

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
