# VM and container startup benchmark

Run from the repository root with an idle NIEP daemon. The default sizes are
1, 2, 4, 8, 16, 32 and 64, tested in three randomized rounds, each measuring every
platform/size once. One discarded warmup precedes each combination's first measured
trial. `--counts` accepts
positive integers, for example `--counts 3 7 64 257`.
Each scenario has one Mininet probe host `h1`, one common switch `s1`, and all
VMs or containers attached to that switch. All data NICs share `10.0.0.0/8`.
NIEP starts its regular switch with its implicit local POX controller; switch
and controller startup are included in `topoup` timing. Run one benchmark at a time and avoid
sending other lifecycle commands to the daemon during a run.

## Prepare outside the measured interval

The VM base needs the current procedural guest network service. The runner
checks the actual disk before any trial. Update an existing base without
rebuilding or changing its SSH keys (requires `qemu-img`, `sfdisk`, `debugfs`,
`e2fsck`, and approximately 5 GiB of temporary disk space):

```sh
.venv/bin/python benchmarks/startup/prepare-image.py \
  VEM/IMAGES/alpine-http.qcow2 \
  --output benchmarks/startup/output/procedural/alpine-http.qcow2
# Keep a backup, then install only while the daemon has no topology defined:
cp VEM/IMAGES/alpine-http.qcow2 /tmp/alpine-http-original.qcow2
sudo install -m 0444 benchmarks/startup/output/procedural/alpine-http.qcow2 \
  VEM/IMAGES/alpine-http.qcow2

docker build -t niep-bench-http:alpine3.20 benchmarks/startup/container
```

Choose a fresh output path when preparing another image: the helper refuses to
overwrite its output. It installs `/etc/init.d/niep-network` with executable
permissions and verifies the resulting filesystem and QCOW2. It preserves the
source disk, guest SSH keys, credentials, and any existing explicit network map.
Without `--output` it checks the installed service; `--count` validates capacity
and accepts positive integers rather than a fixed list. An update supports all
subsequent sizes without needing another map or another image modification.
The runner checks `NIEP_ROOT/VEM/IMAGES/alpine-http.qcow2`, or the repository base
by default; use `--vm-image` to match a daemon using a custom asset directory.
New images built by `benchmarks/images/alpine-http/build.sh` already contain the
service and do not need `--network-map` for this benchmark.

## Procedural addressing

The benchmark's static `network-map` has been removed. The probe host uses
`10.0.0.1/8`; zero-based instance index `i` selects address `10.0.0.0 + i + 2`,
with the same `/8` prefix. There is one shared broadcast domain:

```text
                    +-- VM/container 1: 10.0.0.2/8
h1: 10.0.0.1/8 -- s1 +-- VM/container 2: 10.0.0.3/8
                    +-- VM/container N: 10.0.0.(N+1)/8 (with octet carries)
```

`h1` probes all endpoints concurrently, each using its own unique destination IP.
VM and container scenarios use the same topology and addresses in separate
trials. VM management remains on the separate libvirt DHCP network.

MACs encode the index in four bytes: data `02:01:xx:xx:xx:xx`, management
`02:02:xx:xx:xx:xx`, probe host `02:03:xx:xx:xx:xx`, bridge
`02:04:xx:xx:xx:xx`. These are locally administered unicast addresses. The guest
recognizes the data prefix and computes its IP at boot. Management continues to
use DHCP. An explicit `/etc/niep-network.conf` entry takes precedence, preserving
custom-image and tutorial behavior; avoid overriding benchmark data MACs there.
The optional map mechanism remains available for unrelated custom topologies.

There are 16,777,213 endpoint addresses in this `/8` after reserving the network,
broadcast and probe-host addresses. Counts beyond this pool are rejected.
Host memory, disk, switch-port and runtime capacity impose practical limits much
sooner. Reusing these deterministic IDs/MACs across simultaneous benchmark runs
is unsupported. MAC/IP generation handles octet carries.

This shared-switch version changes the network and startup overhead compared
with historical isolated-link trials. Keep those runs separate when comparing
results; `run_id` and timestamps distinguish executions.

The container uses Alpine 3.20.10 and BusyBox extras 1.36.1-r31, matching the VM
workload. Both serve the exact two bytes `ok` at port 8080, path `/health`.
The image is built and checked locally before timing; no package installation
runs at container startup. VMs use 256 MiB and one vCPU. NIEP's container schema
does not expose CPU/memory limits, so containers use host defaults: this compares
orchestration with an equivalent HTTP workload, not equal resource reservations.
Guest RAM demand is `count * 256 MiB` (64 VMs need 16 GiB), plus host overhead
and room for `count` private disk copies. Both VM disks and container writable layers are recreated
for each trial; host filesystem caches are not flushed.

## Run

```sh
.venv/bin/python benchmarks/startup/run.py
```

Useful options:

```sh
# Quick functional check with a prepared VM base:
.venv/bin/python benchmarks/startup/run.py --counts 1 --repeats 1
# Containers only, one measured trial (plus one warmup) at each size:
.venv/bin/python benchmarks/startup/run.py --kinds container --repeats 1
# Inspect all generated JSON without contacting the daemon:
.venv/bin/python benchmarks/startup/run.py --generate-only
# Choose another shared results directory (created if needed):
.venv/bin/python benchmarks/startup/run.py --output /tmp/niep-startup-trial \
  --socket /run/niep.sock --timeout 180 --repeats 5
# Reproduce a randomized schedule with the same configuration:
.venv/bin/python benchmarks/startup/run.py --repeats 3 --seed 12345
```

`--repeats X` runs X complete measured rounds. Each round independently shuffles
the selected instance counts. In the measured schedule, the VM and container
trials for each size stay adjacent; round 1 also inserts each combination's warmup
immediately before its first measurement. In each block of two sizes, the runner shuffles `[container, vm]` to
choose the first platform for each size: one starts with containers, the other
with VMs. The second platform at each size runs immediately afterward. The next
block draws again. With an odd number of sizes, the final size gets a randomly
chosen first platform. With a single selected platform, only the size order is
shuffled. Repeated counts or platform selections are deduplicated, so each distinct
combination runs exactly once per round.

For example, size order `2, 1, 4, 8` and first-platform choices `C, V, V, C`
(blocks `CV` then `VC`) produce these measured trials:

```text
2C - 2V - 1V - 1C - 4V - 4C - 8C - 8V
```

Both draws are repeated in the next round; chance can produce the same order.
The CSV `repeat` field is the round number (1 through X). `--seed INTEGER` uses a
local random generator to reproduce the schedule with the same selections and
script/Python version. Without it, a new seed is generated and printed as
`Randomization seed: ...`; retain this console output with experimental results.
The console also marks each round. Earlier grouped-order runs should be kept
separate when comparing experimental results.

Every invocation performs exactly one warmup for each distinct `(kind, count)`
combination, immediately before that combination's measured trial in round 1.
Subsequent rounds do not add more warmups for that combination.
`--repeats` counts only measured rounds: `--repeats 1` runs a warmup and then
one measured trial per combination. Defaults therefore launch 14 warmups and 42
measured trials (56 complete lifecycle cycles). `--generate-only` runs neither.

Warmup uses the same topology, HTTP readiness checks, settling period, resource
observation window, optional runtime instrumentation, host memory snapshots, disk collection and
`topodown`/`topodestroy` cleanup as measured trials. Its startup, usage, runtime and
host memory and disk records are discarded, and no statistical summary is computed or
printed. Only warmup progress and diagnostics appear in the console; no warmup
rows enter any CSV or plot. CSV schemas and measured repeat numbers (1 through
`--repeats`) remain unchanged. Keep historical runs without warmup separate when
comparing experimental results.

Warmup failures stop the run by default. `--keep-going` continues into measured
repetitions after ordinary warmup failures, while retaining a nonzero final exit
status. Cleanup failure always stops the series. Interrupting a warmup attempts
cleanup, discards its results and exits with code 130.

`NIEP_SOCKET` also selects the socket. The script refuses to replace an existing
topology. Each trial attempts `topodown` then `topodestroy`, including after startup
or HTTP failure and Ctrl+C. Ctrl+C saves an interrupted measured trial to CSV and exits
with code 130 without a traceback. Cleanup failure stops the series. Keep the terminal
open until cleanup finishes; SIGKILL cannot be handled. Use a dedicated daemon;
the idle check is not an exclusive lock.

## Results and interpretation

Each execution appends measured-trial raw measurements to five CSVs in
`benchmarks/startup/output/` (`--output DIR` selects another shared directory):

| File | Rows | Measurements |
| --- | --- | --- |
| `startup.csv` | One per instance per scenario/repetition | `probe_method`, `started_at`, `define_ms`, `topoup_ms`, `ready_ms`, `status`, `error` |
| `runtime_startup.csv` | One per instance per scenario/repetition | `start_call_ms`, `runtime_ready_ms`, `probe_path`, `status`, `error` |
| `usage.csv` | One per instance per poll | `sample_index`, `sample_timestamp`, `elapsed_seconds`, `memory_bytes`, `cpu_percent`, `status`, `error` |
| `host_memory.csv` | Two per scenario/repetition | `phase`, `sample_timestamp`, `mem_total_bytes`, `mem_available_bytes`, `mem_free_bytes`, `buffers_bytes`, `cached_bytes`, `status`, `error` |
| `disk_usage.csv` | One per instance at scenario end | `sample_timestamp`, `disk_bytes`, `file_bytes`, `source`, `status`, `error`, `image_id`, `image_bytes`, `image_source`, `image_error` |

All five files include `run_id`, `scenario_id`, `kind` (`vm` or `container`), `count`
(number of instances in the scenario), and `repeat`. The instance-level files also
include `instance`; the host snapshots apply to the entire scenario. `run_id` identifies
an invocation; a fresh `scenario_id` identifies each scenario/repetition, including
repeated sizes in the same invocation. Join on **`run_id`, `scenario_id`, `instance`**
for instance-level analysis. Group by `run_id, scenario_id` for a whole scenario.
For example, after loading both CSVs into SQL tables:

```sql
SELECT s.kind, s.count, s.repeat, s.instance, s.ready_ms,
       u.sample_index, u.memory_bytes, u.cpu_percent
FROM startup AS s
JOIN usage AS u
  ON s.run_id = u.run_id
 AND s.scenario_id = u.scenario_id
 AND s.instance = u.instance;
```

The files contain no configuration JSON, summary columns, or
record-type column. Existing rows are retained and headers are written once.
The previous combined `results.csv` is preserved as historical data and is no
longer updated or automatically imported. Incompatible headers in the new CSVs
are rejected before either file is changed. Writes to the output directory are
locked to prevent concurrent benchmark writers.

Post-`topoup` HTTP probing now uses `probe_method=mininet_parallel_http_v1` in
`startup.csv`. Historical sequential-probe files lack this column and their
headers are rejected rather than rewritten. Use a fresh `--output` directory
(for example, `--output benchmarks/startup/output/parallel-http-v1`) for new
measurements, and pass that directory as `--input` when plotting. Keep sequential
and concurrent-probe runs separate: the plotter does not enforce methodology
compatibility when explicitly pooling run IDs.

Topology descriptors are temporary and removed after execution, including after
handled interruption. `--generate-only` explicitly saves descriptors under
`DIR/topologies/` for inspection, without recording benchmark results.

After all instances answer HTTP, each trial waits **2 seconds**, seeds the CPU
counter baseline, then keeps all instances alive for a **10-second** observation
window with polling every **1 second**. The baseline is excluded from results,
so CPU deltas do not include the settling period. Defaults can be changed with
`--settle-seconds`, `--observe-seconds` and `--stats-interval`. The daemon must
support the `stats` command; this is checked before launching a topology.

Samples are flushed immediately, including before an interruption or cleanup
failure. Startup rows are saved after cleanup and retain readiness timings plus
any failure information. With default settings a complete trial produces
`count` startup rows and `10 * count` usage rows. Failed startup/timeouts skip
resource observation and still attempt cleanup.

The script prints these derived statistics in English without writing them to CSV:

- Mean scenario memory: mean of the total VM/container memory at each poll.
- Mean memory/platform: mean of all per-instance memory observations.
- P95 memory/platform: nearest-rank p95 over those same observations.
- Mean scenario CPU: mean of summed VM/container CPU at each poll.
- Mean CPU/platform: mean of all per-instance CPU observations.

Printed memory uses MiB; CSV memory uses bytes. CPU uses 100% per occupied core.
Only the scenario's VMs/containers enter these statistics; the daemon is excluded.
Memory uses QEMU RSS for VMs and cgroup usage including cache for containers, as
reported by `niepd stats`. Total averages use only complete polls; absent values
are never silently counted as zero. Incomplete samples mark the trial as failed.
Polling deadlines are relative to the baseline; slow requests skip missed ticks
rather than issuing a burst, and actual collection times are recorded. The
10-second setting excludes the initial 2-second wait and can overrun slightly
while the last request completes. Other `stats` clients share the daemon's CPU
sampling history, so CPU intervals may be shorter than the benchmark interval.
These are observations of the running HTTP service without additional load.

### Raw host memory snapshots

The runner reads Linux `/proc/meminfo` on the same host as the local NIEP daemon,
without spawning a process or requesting daemon resource statistics. Each
measured scenario/repetition that attempts `topoup` records two snapshots:

- `before_topoup`: after `define` and runtime timing setup, immediately before
  starting the `topoup` timer and invoking the command.
- `before_topodown`: after resource observation, runtime timing and disk collection,
  immediately before invoking `topodown`, while the scenario is still running.

`host_memory.csv` stores raw `MemTotal`, `MemAvailable`, `MemFree`, `Buffers`, and
`Cached` counters as integer bytes (`kB` from procfs multiplied by 1024), plus a UTC
`sample_timestamp`. It stores neither used-memory estimates nor deltas. Join these
rows to the scenario using **`run_id`, `scenario_id`**; do not sum or duplicate the
host readings per instance. Both snapshots are flushed after cleanup so CSV writes
do not intervene between the final snapshot and `topodown`. Existing instance-level
CSV headers are unchanged; the new file is created alongside them, including with
`--skip-runtime-timing`.

The plot estimates used host memory as `MemTotal - MemAvailable` and computes
`after - before` once per trial. With unchanged `MemTotal`, this equals
`MemAvailable_before - MemAvailable_after`. Positive values mean estimated used
memory increased; negative values are retained. The kernel defines `MemAvailable`
as an estimate of memory available for new applications without swapping, including
reclaimability considerations ([Linux procfs documentation](https://docs.kernel.org/filesystems/proc.html)).
This is a host-wide before/after estimate, including orchestration and host services;
background processes, memory reclamation and cache changes can affect it. It is not
a peak measurement, a time average, or memory attributed exclusively to the scenario.

Startup failure, HTTP timeout or interruption still attempts the final snapshot
before cleanup; failed `topoup` may already have rolled back resources. A failure
before the first snapshot (for example, `define` failure) produces no host pair.
Missing/invalid counters produce `metrics_error` and empty values, preserving startup
timings and cleanup. The run reports a collection failure and exits nonzero (or
continues with `--keep-going`). The plot uses only successful, complete startup
scenarios with exactly one valid host snapshot per phase and unchanged `MemTotal`;
missing or invalid pairs are never replaced with zero.

### End-of-scenario private disk usage

The runner checks `niepd disk-usage` support before launching any trial. At the end
of each scenario that attempted `topoup`, it requests one disk snapshot after
resource observation and runtime timing collection, while the instances still
exist. This happens before the final host-memory snapshot and `topodown`; disk
scanning can affect host caches and therefore the subsequent memory estimate.
Warmup runs perform the same collection but discard the results.

`disk_usage.csv` stores one row per expected instance, joined using **`run_id`,
`scenario_id`, `instance`**, with the daemon's UTC `sample_timestamp` and raw bytes:

- VMs: `disk_bytes` is allocated blocks of the private QCOW2 file (`st_blocks * 512`),
  with `source=host_allocated_blocks`. `file_bytes` is the host file's logical length,
  not guest virtual disk capacity.
- Containers on a local Unix-socket Engine: prefer allocated blocks of the private
  writable layer (`source=host_allocated_blocks`), including directories and
  counting hardlinks once without following symlinks. The layer is located from
  `GraphDriver.Data.UpperDir`, or the running container's root OverlayFS mount
  in `/proc/PID/mountinfo` for containerd image stores.
- When that directory is unavailable, inaccessible, or the Engine is remote, use
  Docker's `SizeRw` (`source=docker_writable_layer`). This is a driver-accounted
  content-size estimate, not allocated host blocks. `file_bytes` is empty for
  containers with either method. Check `source` before comparing historical runs
  or combining runs from different hosts; the plot accepts both methods.

`disk_bytes` remains private instance storage. VM instances are full QCOW2
copies, so their measured allocation already includes the base content once per
instance; never add or multiply the base image again. Container rows additionally
record `image_id`, `image_bytes`, `image_source=docker_image_size` and `image_error`.
The daemon inspects the immutable image used by each container, caching its
Docker `Size` once per snapshot; this estimates image content size rather than
allocated host blocks. The plot adds that size once per distinct image ID to the
sum of writable layers. Aliases of the same image are counted once. The benchmark
uses one image for all containers; for scenarios with different images, common
layers between different image IDs are not deduplicated, so the sum can overestimate.
Volumes, bind mounts, runtime/container logs outside the instance disk, and runtime
metadata remain excluded. The stored VM source template is also excluded; the
comparison counts the copies required to run the instances. The measurements are read while running, without forcing a disk flush;
the daemon collects resources sequentially, so the snapshot is not atomic.

Values are flushed after cleanup. Missing instances, unavailable storage counters
and collection failures are written with an error status and empty sizes rather
than zero. A genuine empty writable layer remains a valid zero. Cleanup is still
attempted and valid startup timings are preserved. Collection failures make the
run exit nonzero; `--keep-going` continues after ordinary failures. Failed startup
or interrupted trials attempt collection before cleanup but are excluded from the
comparison plot. A failure before attempting `topoup` produces no disk rows.

The image fields extend `disk_usage.csv`; use a new `--output` directory when
collecting after this update. The runner rejects incompatible existing headers
without modifying them. The file is created even with `--skip-runtime-timing`.
Historical files remain readable by the plotter: they retain the private-storage
curve, but container observations without image metadata are omitted from the
including-images curve rather than presenting private storage as the total.
Image collection errors are kept in `image_error`, preserve private counters and
startup timings, and make the benchmark exit nonzero.

By default the first failed trial stops the series and prints its diagnostic;
`--keep-going` continues after ordinary failures. Nonzero exit means a trial failed.

- `started_at`: UTC time just before starting the scenario/repetition.
- `define_ms`: topology definition, excluded from startup timing.
- `topoup_ms`: wall time for the blocking NIEP startup command.
- `ready_ms`: milliseconds from just before `topoup` to observing HTTP 200 with
  exact body `ok` for that instance through Mininet. Compute the maximum per
  scenario to obtain the time when all instances were ready.
- `sample_index`: scheduled poll number (may skip numbers for slow requests).
- `sample_timestamp`: UTC timestamp supplied by the daemon.
- `elapsed_seconds`: actual elapsed observation time since the CPU baseline.
- `status` and `error`: readiness, timeout, metrics or cleanup failure details.

The clock is monotonic. Probing begins after `topoup` returns because NIEP exposes
Mininet commands only after topology startup. NIEP starts resources sequentially;
these are end-to-end topology observations, not individual hypervisor/process
boot durations. A single command launches `http-probe.py` inside `h1`, using the
runner's Python interpreter and one asynchronous task per endpoint. Each task
retries independently, with at most 300 ms per HTTP attempt and `--interval`
between attempts. Every task uses the original start time and shared deadline
from before `topoup`; on Linux the monotonic performance clock is shared across
these processes on the same host. The collector bypasses HTTP proxies and requires
HTTP 200 with exact body `ok`. It records each response's observation time locally,
so waiting for other endpoints and returning the final JSON do not inflate
`ready_ms`. Initial CLI/socket/interpreter startup, polling delay and event-loop
scheduling are still included. A runner-owned temporary marker cancels outstanding
tasks when the runner unwinds after interruption or command failure, allowing
topology cleanup to proceed. The benchmark sets
`NIEP_CLIENT_TIMEOUT` to `--rpc-timeout` (600 seconds by default), so larger
topologies do not hit the regular CLI response timeout of 10 seconds. Fast containers may already
be ready by the first observation. `--timeout` is the HTTP deadline counted from
before `topoup`; it does not cancel a blocking daemon lifecycle operation.
Record the host configuration, base QCOW2 checksum and package manifest alongside
the output when collecting experimental results. Warmup exercises the startup path
and caches, but does not enforce a particular cache state. Trial order is randomized
as described above; background load and CPU frequency remain uncontrolled.

## Large switch startup

NIEP starts OVS through Mininet's batch API and a checked subprocess, avoiding
Mininet's interactive PTY. At 64 VM ports the generated OVS command exceeds the
terminal's roughly 4 KiB canonical line limit; older NIEP versions could report
a successful `topoup` even though the switch bridge was not created. The fixed
executor executes the full command outside that terminal and propagates OVS
command failures into startup rollback. Restart `niepd` after updating the code.
Previously recorded timeout rows are retained; rerun affected scenarios, e.g.:

```sh
.venv/bin/python benchmarks/startup/run.py --counts 64 --repeats 1
```

## Plot results with Matplotlib

```sh
# Optional dependency (if Matplotlib is not already installed):
.venv/bin/pip install -e '.[benchmark]'

# Latest run, Portuguese and English PNGs under output/plots/pt/ and output/plots/en/:
.venv/bin/python benchmarks/startup/plot.py

# Select comparable runs explicitly to combine repetitions:
.venv/bin/python benchmarks/startup/plot.py --run-id RUN_ID_1 RUN_ID_2

# Use another output directory:
.venv/bin/python benchmarks/startup/plot.py --input benchmarks/startup/output \
  --output /tmp/niep-figures
```

Eleven figures are generated in each language (twenty-two PNGs total). Portuguese titles,
axes and legends are under `plots/pt/`; English versions are under `plots/en/`.
Only PNG is generated:

- `topoup_time`: blocking topology startup command duration versus instance count.
- `startup_time`: time until all instances answer HTTP versus instance count.
- `runtime_start_call`: mean per-instance runtime start API duration (ms) versus count.
- `runtime_http_ready`: mean per-instance runtime start-to-HTTP duration (ms) versus count.
- `cpu_mean`: mean aggregate CPU versus instance count.
- `memory_mean`: mean aggregate memory versus instance count.
- `host_memory_delta`: estimated host used-memory change between the two snapshots
  versus instance count, comparing VMs and containers (MiB).
- `disk_usage`: estimated scenario disk usage including images versus instance
  count (MiB): full private VM copies, or container writable layers plus each
  distinct Docker image once.
- `disk_usage_private`: private instance disks/writable layers only, preserving
  the previous comparison and showing where container growth comes from.
- `cpu_per_instance`: VM/container bars normalized to usage per instance,
  pooling the selected scenario sizes.
- `memory_per_instance`: the analogous normalized memory bars.

The two runtime timing curves read `runtime_startup.csv` when present and join
`run_id`, `scenario_id`, `instance` back to the selected successful startup trials.
They use only complete runtime captures. For each trial,
the individual durations are averaged once across its instances; plotted means
and standard deviations then use those trial-level means. These are per-instance
durations, not the total startup time or a sum over N. Historical runs without
runtime instrumentation show no observation for those curves, rather than zero.

The host memory curve reads `host_memory.csv` when present, joins on `run_id` and
`scenario_id`, and contributes one delta per trial, regardless of instance count or
poll count. It shows the mean and ±1 sample standard deviation across repetitions
at each size. A zero reference line makes negative deltas visible. Historical runs
without host snapshots retain all other plots and show no host delta observations.

Both disk curves read `disk_usage.csv` when present and require exactly one
successful private measurement for each expected instance, validating kind, count,
repeat and source. The private curve sums `disk_bytes`; the including-images curve
also requires valid, consistent container image metadata and adds each image once
per scenario. Both plot mean and ±1 sample standard deviation across repetitions
at each size. Neither uses logical `file_bytes` or treats instances as independent
repetitions. Missing image data never becomes a zero-byte image.
The disk charts use a logarithmic Y axis and label the point values in MiB so
small container layers remain visible alongside full VM disk copies. When a
scenario has a genuine zero, a symmetric logarithmic axis with a linear region
below 1 KiB preserves that zero instead of dropping or replacing it.

`topoup_time` takes exactly one `topoup_ms` value per scenario/repetition,
converted to seconds. The repeated copies in instance rows do not count as
independent observations. Different `topoup_ms` values in the same scenario are
rejected as inconsistent; missing timings are not replaced by zero. Error bars
show variation across repetitions of each scenario size. This command duration
ends before the subsequent HTTP scan, settling wait, and resource polling.

Startup time is the maximum `ready_ms` across all instances in a successful
scenario/repetition, converted to seconds. For resources, complete polling rounds
are summed across instances, then averaged over time within that trial. Curves
show the mean of trial-level observations at each size, with error bars of
**±1 sample standard deviation** across repetitions (`ddof=1`). They do not treat
polling rows or multiple VMs in the same trial as independent repetitions.
With only one trial at a size, its standard deviation is unavailable and the
figure draws no error bar. Sample-count annotations are omitted from all
figures; trial counts are printed only in the console. Run with
`--repeats 3` or more to measure between-trial variation.

For each bar, each trial's mean aggregate usage is divided by its instance count.
The bar and error bar are the mean and sample standard deviation across these
normalized trial observations, including all selected sizes. Every trial has
equal weight; larger topologies and trials with more polls do not dominate.
This SD describes variation between normalized trials/sizes, not the dispersion
of individual platform measurements within one polling round.

The script defaults to the most recently written run ID and prints the selected
IDs and included scenario counts. `--run-id all` pools all historical runs: use
only if topology, workload and configuration are comparable. In particular, do
not pool earlier isolated-link and current shared-switch experiments blindly.

You may run plotting while a benchmark is appending data. Files are read as
snapshots without locking or modifying the CSVs. Failed/incomplete scenarios,
incomplete polls and orphan usage rows from an unfinished trial are excluded.
Successful startup scenarios without complete resource polls still contribute
to the startup graph, while missing resource metrics are never replaced by zero.
Re-run plotting after the benchmark completes to refresh all figures; existing
figures in the chosen output directory are replaced. The backend is `Agg`, so a
GUI or display server is not required. No derived columns are written to CSV.

## Per-instance runtime startup in the main trial

The normal command now measures the **same VM/container instances** used by the
scenario and writes `runtime_startup.csv` automatically:

```sh
.venv/bin/python benchmarks/startup/run.py --counts 1 2 --repeats 1
```

Update/restart `niepd` before using this feature. The benchmark checks support
before launching a topology. No second boot or separate script is required.
Use `--skip-runtime-timing` to disable it and retain startup, usage, host memory and disk CSVs.
The existing 2-second settling period and 10-second CPU/memory observation window
remain after the whole topology answers HTTP.

Before `topoup`, the script arms a one-shot capture in the daemon. Hooks directly
around libvirt's `domain.create()` and Docker's `container.start()` capture each
start. HTTP probes begin concurrently with those actual API calls, rather than
waiting for `topoup` or Mininet to finish. Image lookup, disk copying, domain
XML definition and container object creation happen before these timers.
Mininet link attachment, switch startup and later topology management are not
prerequisites for the readiness probes.

`runtime_startup.csv` contains the same foreign keys **`run_id`, `scenario_id`,
`kind`, `count`, `repeat`, `instance`** as `startup.csv` and `usage.csv`.
These rows measure the same instances as the topology trial. Fields:

- `started_at`: UTC time immediately before invoking the runtime start API.
- `start_call_ms`: wall-clock duration until that API returns (including runtime
  communication and the work it performs to start the already-prepared instance).
  For VMs this invokes libvirt domain startup; for containers this invokes the
  Docker Engine start operation. It is not an HTTP readiness or complete boot
  time. Subsequent Docker reload/status checks are outside this interval.
- `runtime_ready_ms`: from that same API invocation until the first observed
  HTTP 200 with exact body `ok`. Because probing is concurrent, this can even be
  smaller than `start_call_ms` if HTTP responds before the API returns.
- `runtime_id`: the actual VM UUID or Docker container ID.
- `probe_path`: `libvirt_management_dhcp` for VMs; `container_loopback` for
  containers. Loopback is probed inside the existing container's network namespace
  using `nsenter`; no second container or guest credentials are involved.
- `status`, `error`: readiness, timeout, start/probe or collection failures.

The daemon uses monotonic clocks and a 100 ms probe interval. VM management
address discovery, network/HTTP initialization and observation delay are part
of `runtime_ready_ms`. Container observations include launching the small probe
process in its namespace. These add measurement overhead and yield observational
upper bounds, not exact guest-kernel or application process boot durations.
The probe runs while other instances and the NIEP topology are starting: resource
contention remains. The subsequent settling wait does not enter startup timers.

The original `startup.csv` `ready_ms` still measures from just before `topoup`
to HTTP observed through the shared Mininet data network. The runtime CSV starts
later and probes another network path. Comparing these is useful, but subtracting
them is not an exact decomposition of NIEP orchestration overhead.

No derived statistics or configuration JSON is stored. For example:

```sql
SELECT s.kind, s.count, s.instance, s.ready_ms, r.runtime_ready_ms, r.start_call_ms
FROM startup s JOIN runtime_startup r
  ON s.run_id = r.run_id AND s.scenario_id = r.scenario_id AND s.instance = r.instance
WHERE r.status = 'ready';
```

For manual diagnostics, the command API/CLI supports:

```sh
niepctl --json startup-timing arm 180 0.1
niepctl topoup
niepctl --json startup-timing snapshot
niepctl --json startup-timing disable
```

A capture applies to one `topoup`, never to unrelated later starts. Topology stop,
clean/destroy or a failed start cancels pending probes. The main benchmark saves
one timing row per expected instance before cleanup, including missing-event or
collection errors, and checks that the capture identity has not changed.

## Sequential launch and observation latency

NIEP's operation journal executes lifecycle steps sequentially: each VM is
created/configured/started before advancing to the next; each container is
created/started and connected before the next. Once started, its guest/process
continues initialization concurrently with later orchestration. The scheduler
does not wait for one instance to answer HTTP before launching the next.

After `topoup`, `ready_ms` uses concurrent HTTP observations through `h1`. A slow
or unreachable endpoint no longer holds up probes of the other endpoints. The
collector still cannot observe a service before `topoup` returns, and large N
can add event-loop and network contention. `runtime_ready_ms` uses concurrent
probes starting at each actual runtime start and avoids waiting for `topoup`.
These raw durations
cannot be multiplied by N to predict the full scenario time: object creation,
network setup, switch/controller startup, resource contention and observation
latency are different components, and boot progress overlaps.
