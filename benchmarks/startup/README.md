# VM and container startup benchmark

Run from the repository root with an idle NIEP daemon. The default sizes are
1, 2, 4, 8, 16, 32 and 64, first VMs and then containers, with three trials per
size. `--counts` accepts positive integers, for example `--counts 3 7 64 257`.
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

`h1` probes every endpoint sequentially using its own unique destination IP.
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
# Containers only, one trial at each size:
.venv/bin/python benchmarks/startup/run.py --kinds container --repeats 1
# Inspect all generated JSON without contacting the daemon:
.venv/bin/python benchmarks/startup/run.py --generate-only
# Choose another shared results directory (created if needed):
.venv/bin/python benchmarks/startup/run.py --output /tmp/niep-startup-trial \
  --socket /run/niep.sock --timeout 180 --repeats 5
```

`NIEP_SOCKET` also selects the socket. The script refuses to replace an existing
topology. Each trial attempts `topodown` then `topodestroy`, including after startup
or HTTP failure and Ctrl+C. Ctrl+C saves the interrupted trial to CSV and exits
with code 130 without a traceback. Cleanup failure stops the series. Keep the terminal
open until cleanup finishes; SIGKILL cannot be handled. Use a dedicated daemon;
the idle check is not an exclusive lock.

## Results and interpretation

Each execution appends raw measurements to two CSVs in
`benchmarks/startup/output/` (`--output DIR` selects another shared directory):

| File | Rows | Measurements |
| --- | --- | --- |
| `startup.csv` | One per instance per scenario/repetition | `started_at`, `define_ms`, `topoup_ms`, `ready_ms`, `status`, `error` |
| `usage.csv` | One per instance per poll | `sample_index`, `sample_timestamp`, `elapsed_seconds`, `memory_bytes`, `cpu_percent`, `status`, `error` |

Both files include `run_id`, `scenario_id`, `kind` (`vm` or `container`), `count`
(number of instances in the scenario), `repeat`, and `instance`. `run_id` identifies
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

The files contain no configuration JSON, image metadata, summary columns, or
record-type column. Existing rows are retained and headers are written once.
The previous combined `results.csv` is preserved as historical data and is no
longer updated or automatically imported. Incompatible headers in the new CSVs
are rejected before either file is changed. Writes to the output directory are
locked to prevent concurrent benchmark writers.

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
boot durations. Probes run round robin, with at most 300 ms per HTTP attempt;
CLI/socket overhead and polling delay are included. The benchmark sets
`NIEP_CLIENT_TIMEOUT` to `--rpc-timeout` (600 seconds by default), so larger
topologies do not hit the regular CLI response timeout of 10 seconds. Fast containers may already
be ready by the first observation. `--timeout` is the HTTP deadline counted from
before `topoup`; it does not cancel a blocking daemon lifecycle operation.
Record the host configuration, base QCOW2 checksum and package manifest alongside
the output when collecting experimental results. These functional scripts do not
control cache warmth, background load, CPU frequency or experiment ordering.

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

Five figures are generated in each language (ten PNGs total). Portuguese titles,
axes and legends are under `plots/pt/`; English versions are under `plots/en/`.
Only PNG is generated:

- `startup_time`: time until all instances answer HTTP versus instance count.
- `cpu_mean`: mean aggregate CPU versus instance count.
- `memory_mean`: mean aggregate memory versus instance count.
- `cpu_per_instance`: VM/container bars normalized to usage per instance,
  pooling the selected scenario sizes.
- `memory_per_instance`: the analogous normalized memory bars.

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
