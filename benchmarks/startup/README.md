# VM and container startup benchmark

Run from the repository root with an idle NIEP daemon. The default sequence is
1, 2, 4, 8, 16 VMs, followed by 1, 2, 4, 8, 16 containers, with three fresh trials
per size. Each instance has an independent link to its own Mininet probe host.
No controller or switch startup is included. Only one benchmark may run at once;
do not send other lifecycle commands to the daemon during a run.

## Prepare outside the measured interval

The VM base must configure all 16 data MACs at boot. The runner now verifies the
actual disk contents before any trial and stops immediately if mappings are
missing. To adapt an existing base without rebuilding or changing its SSH keys,
create a corrected offline copy (requires `qemu-img`, `sfdisk`, `debugfs` and
`e2fsck`, and approximately 5 GiB of temporary disk space):

```sh
.venv/bin/python benchmarks/startup/prepare-image.py \
  VEM/IMAGES/alpine-http.qcow2 \
  --output benchmarks/startup/output/prepared/alpine-http.qcow2
# Keep a backup, then install only while the daemon has no topology defined:
cp VEM/IMAGES/alpine-http.qcow2 /tmp/alpine-http-original.qcow2
sudo install -m 0444 benchmarks/startup/output/prepared/alpine-http.qcow2 \
  VEM/IMAGES/alpine-http.qcow2
```

The helper never edits its source and refuses to overwrite its output. It changes
only `/etc/niep-network.conf` in the new disk, verifies filesystem integrity and
checks QCOW2 consistency. Running without `--output` checks the map only. The
runner uses `NIEP_ROOT/VEM/IMAGES/alpine-http.qcow2`, or the repository base by
default; `--vm-image` must match the daemon's registered base when using a custom
asset directory.

Alternatively, rebuild from pinned packages with the supplied map:

```sh
sudo benchmarks/images/alpine-http/build.sh \
  --authorized-keys "$HOME/.ssh/niep-bench.pub" \
  --network-map benchmarks/startup/network-map \
  --output "$PWD/benchmarks/images/alpine-http/output/startup16"
sudo install -m 0444 \
  benchmarks/images/alpine-http/output/startup16/alpine-http-base.qcow2 \
  VEM/IMAGES/alpine-http.qcow2

docker build -t niep-bench-http:alpine3.20 benchmarks/startup/container
```

Use your own SSH public key. Never replace a base used by an active topology.
The 16 mappings intentionally use the same IP on separate, isolated data links;
MACs, interface IDs, management MACs and VM IDs are unique. Do not connect these
links into a common broadcast domain without changing the address plan.

The container uses Alpine 3.20.10 and BusyBox extras 1.36.1-r31, matching the VM
workload. Both serve the exact two bytes `ok` at port 8080, path `/health`.
The image is built and checked locally before timing; no package installation
runs at container startup. VMs use 256 MiB and one vCPU. NIEP's container schema
does not expose CPU/memory limits, so containers use host defaults: this compares
orchestration with an equivalent HTTP workload, not equal resource reservations.
16 VMs require at least 4 GiB of guest RAM plus host overhead and room for 16
private disk copies. Both VM disks and container writable layers are recreated
for each trial; host filesystem caches are not flushed.

## Run

```sh
.venv/bin/python benchmarks/startup/run.py
```

Useful options:

```sh
# Quick functional check with the current one-MAC VM base:
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

All executions append to **`benchmarks/startup/output/results.csv`** by default.
`--output DIR` chooses a different shared directory. Existing rows are retained,
and the header is written only once. Each row has `run_id` and UTC `started_at`
to distinguish executions, `config_json` with the invocation settings, and
`image_id` with the inspected Docker image ID when containers are included.
Topology descriptors are temporary and removed after execution, including after
handled interruption. `--generate-only` explicitly saves descriptors under
`DIR/topologies/` for inspection, without recording benchmark results.

A CSV row is saved for every instance after each trial, including failures and
timeouts. By default the first failed trial stops the series and prints its
diagnostic; `--keep-going` continues after ordinary failures. Nonzero exit means
a trial failed. Concurrent writes to the same CSV are rejected. An incompatible
existing CSV header is rejected without modifying its contents. Historical
CSV files in timestamped directories from older versions remain available.

- `define_ms`: topology definition, excluded from startup timing.
- `topoup_ms`: wall time for the blocking NIEP startup command.
- `ready_ms`: milliseconds from just before `topoup` to observing HTTP 200 with
  exact body `ok` for that instance through Mininet.
- `all_ready_ms`: last observed readiness in the trial; blank if any instance
  failed. This value is repeated in all rows of the same trial; aggregate once
  per `(run_id, kind, count, repeat)` when comparing topology startup times.
- `status` and `error`: readiness, timeout, startup or cleanup failure details.

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
