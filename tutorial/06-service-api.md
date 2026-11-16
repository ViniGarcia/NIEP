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
default. The socket is created as `root:niep` with mode `0660`. Linux peer
credentials are checked in addition to filesystem permissions: root and
members of the explicit `niep` group may invoke daemon operations, while other
local users are rejected before dispatch. Treat `niep` as a root-equivalent
group and add only intended operators. Log out and back in after installation
before using this access for the first time.

To use a different socket:

```bash
make vm-daemon NIEP_SOCKET=/run/niep-dev.sock
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
.venv/bin/niepctl --json status
.venv/bin/niepctl --json define tutorial/examples/mininet-ping.json
.venv/bin/niepctl --json topoup
.venv/bin/niepctl --json mininet pingall
.venv/bin/niepctl --json topodown
```

For large topologies, increase the client response timeout (the default is 10
seconds). This controls how long the CLI waits; it does not cancel an operation
already executing in the daemon:

```sh
NIEP_CLIENT_TIMEOUT=600 .venv/bin/niepctl topoup
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
export NIEP_SOCKET=/run/niep-dev.sock
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

The daemon uses bounded client workers, so an interactive shell does not block
ordinary clients. Interactive sessions have a conservative concurrency and
idle lifetime limit; disconnecting or timing out always closes the private
stream.

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

## Resource usage

Restart `niepd` after upgrading the checkout to load the metrics collector.
Follow CPU and memory usage with client-side polling (Ctrl+C exits):

```sh
niepctl stats                         # default interval: 5 seconds
niepctl stats --interval 2
niepctl stats-snapshot                # one snapshot, always JSON
niepctl --json stats                  # one JSON response per poll (JSON Lines)
```

The socket command is `stats` with no arguments. It returns UTC `timestamp`,
`resources` (the topology's VMs and containers), `daemon`, and `totals` for
`vms`, `containers`, `workloads`, and `with_daemon`. No other host workloads are
included. Mininet processes, external controllers and VNF/SFC-owned VMs are not
included in these totals.

CPU uses cumulative runtime counters between successive daemon samples. 100%
means one fully occupied CPU core, so values can exceed 100%. The first sample
for each running instance has `cpu_percent: null`; after restart or a reset of
its counter, that instance needs another sample. `sample_interval_seconds`
reports the interval used. Snapshots return immediately without waiting to
measure an interval; multiple clients share the daemon's sampling history.

Memory is in bytes: VM `memory_bytes` is libvirt's host QEMU RSS, while container
memory is Docker's cgroup usage including cache. These are different accounting
sources; container values can differ from Docker CLI stats, which subtracts
cache on Linux. `memory_limit_bytes` is configured VM maximum memory or the
container's effective cgroup limit. Daemon memory is RSS and CPU includes its
own threads. Shared pages may be counted in multiple RSS totals.

Stopped resources report zero usage. An unavailable runtime reports an error on
its resource row and unavailable metrics stay null. Aggregates sum known values
and include `cpu_samples`, `memory_samples`, and `partial` so missing samples are
visible; a partial aggregate is not a complete usage total. A failure collecting
one instance does not discard the other instances' measurements. Collection is
sequential, so the snapshot is not an atomic view of all runtimes.

## Topology disk usage

After restarting the updated daemon, inspect storage occupied by the topology:

```sh
niepctl disk-usage
niepctl --json disk-usage
```

The command reports each VM/container and totals for VMs, containers and all
workloads. JSON values are bytes; the table uses MiB. It measures storage, not
read/write I/O rates or free space inside the guest. Its scope matches `stats`:
explicit topology VMs and containers, excluding VNF/SFC-owned VMs.

VM `disk_bytes` counts allocated host blocks (`st_blocks * 512`) in the instance's
QCOW2 file, respecting sparse allocation; `file_bytes` is the host file length,
not the guest disk capacity. For a local Unix-socket Docker Engine, container
`disk_bytes` prefers allocated blocks in its private writable directory, with
`source=host_allocated_blocks`. This includes directory blocks, counts hardlinks
once and does not follow symlinks. Both classic `UpperDir` and running containerd
OverlayFS snapshots are supported. When the directory cannot be located or read,
or the Engine is remote, the fallback is `SizeRw` with
`source=docker_writable_layer`: driver-accounted content size rather than allocated
blocks. Check the source when comparing runs. The combined total remains an
estimate: compression, reflinks, metadata and shared extents affect physical
storage consumption. Scans are not atomic; traversal errors fall back to `SizeRw`
rather than returning a partial allocation count.

The `disk_bytes` counters and CLI totals exclude shared image storage. For
containers, JSON additionally reports `image_id`, `image_bytes`,
`image_source=docker_image_size` and `image_error`. The immutable image ID is taken
from the actual container; its `Size` is cached once per snapshot. To estimate
scenario storage including images, sum private counters and add each distinct
container image once. VM disks are full private copies and already include the
base content: adding their template again would double-count it. Different image
IDs may share layers, so summing their content sizes can overestimate storage;
the startup benchmark uses a single image. Image errors preserve private counters
and are reported separately. Container logs, volumes, bind mounts, VM XML, host
networking and daemon logs are also excluded. Stopped instances remain measurable
while their files/layers exist. An uncreated instance reports zero; unavailable
storage reports null and an error. JSON totals include `partial` and
`measured_resources`; the table reports measured/total instance counts. Collection
is read-only, sequential, and may take longer for large writable layers. No guest
agent or SSH is required. Use `NIEP_CLIENT_TIMEOUT=600 niepctl disk-usage` if needed.
