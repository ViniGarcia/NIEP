#!/usr/bin/env python3
"""Measure NIEP topology startup through HTTP on a shared Mininet switch."""
import argparse
import csv
from contextlib import contextmanager, ExitStack
import fcntl
import json
import math
import statistics
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import tempfile
from uuid import uuid4
from datetime import datetime, timezone

from niep.domain.startup_addressing import PREFIX_LENGTH, addresses, mac, positive_count, validate_count


COUNTS = (1, 2, 4, 8, 16, 32, 64)
COMMON_FIELDS = ('run_id', 'scenario_id', 'kind', 'count', 'repeat', 'instance')
STARTUP_FIELDS = COMMON_FIELDS + ('started_at', 'define_ms', 'topoup_ms', 'ready_ms', 'status', 'error')
USAGE_FIELDS = COMMON_FIELDS + ('sample_index', 'sample_timestamp', 'elapsed_seconds',
                                'memory_bytes', 'cpu_percent', 'status', 'error')
RUNTIME_FIELDS = COMMON_FIELDS + ('runtime_id', 'started_at', 'start_call_ms',
                                  'runtime_ready_ms', 'probe_path', 'status', 'error')
SCHEMAS = {'startup': STARTUP_FIELDS, 'usage': USAGE_FIELDS, 'runtime_startup': RUNTIME_FIELDS}


def mean(values):
    return statistics.fmean(values) if values else None


def p95(values):
    # Nearest-rank percentile, including for small sample sets.
    return sorted(values)[math.ceil(0.95 * len(values)) - 1] if values else None


def summarize(samples, count):
    rounds = {}
    for row in samples:
        rounds.setdefault(row['sample_index'], []).append(row)
    memory_totals, cpu_totals = [], []
    for rows in rounds.values():
        if len(rows) == count and all(r['memory_bytes'] is not None for r in rows):
            memory_totals.append(sum(r['memory_bytes'] for r in rows))
        if len(rows) == count and all(r['cpu_percent'] is not None for r in rows):
            cpu_totals.append(sum(r['cpu_percent'] for r in rows))
    memory = [r['memory_bytes'] for r in samples if r['memory_bytes'] is not None]
    cpu = [r['cpu_percent'] for r in samples if r['cpu_percent'] is not None]
    return dict(scenario_memory_mean_bytes=mean(memory_totals),
                platform_memory_mean_bytes=mean(memory), platform_memory_p95_bytes=p95(memory),
                scenario_cpu_mean_percent=mean(cpu_totals), platform_cpu_mean_percent=mean(cpu))


def observe(client, instances, kind, count, repeat, *, duration, interval, settle, save):
    time.sleep(settle)
    # Seed after settling so the first CPU delta excludes boot and the settling period.
    client.call('stats')
    start = time.monotonic()
    samples = []
    tick = 1
    while tick * interval <= duration + 1e-9:
        time.sleep(max(0, start + tick * interval - time.monotonic()))
        snapshot = client.call('stats')
        elapsed = time.monotonic() - start
        resources = {(r['kind'], r['id']): r for r in snapshot['resources']}
        batch = []
        for ident in instances:
            resource = resources.get((kind, ident), {})
            memory, cpu = resource.get('memory_bytes'), resource.get('cpu_percent')
            error = resource.get('error') or ''
            if resource.get('state') != 'running' or memory is None or cpu is None:
                error = error or 'Resource stopped, missing or metrics unavailable'
            row = dict.fromkeys(USAGE_FIELDS, '')
            row.update(kind=kind, count=count, repeat=repeat,
                       instance=ident, sample_index=tick, sample_timestamp=snapshot['timestamp'],
                       elapsed_seconds=round(elapsed, 6), memory_bytes=memory, cpu_percent=cpu,
                       status='metrics_error' if error else 'sampled', error=error)
            if resource.get('state') != 'running':
                row.update(memory_bytes=None, cpu_percent=None)
            batch.append(row)
        save(batch)
        samples.extend(batch)
        # Skip missed deadlines instead of issuing a burst of delayed requests.
        tick = max(tick + 1, math.floor((time.monotonic() - start) / interval) + 1)
    return samples


def print_summary(kind, count, repeat, summary):
    def value(key, memory=False):
        number = summary.get(key)
        return 'n/a' if number is None else f'{number / 1048576 if memory else number:.2f}'

    print(f'{kind} n={count} repeat={repeat}: '
          f'mean scenario memory={value("scenario_memory_mean_bytes", True)} MiB; '
          f'mean memory/platform={value("platform_memory_mean_bytes", True)} MiB; '
          f'p95 memory/platform={value("platform_memory_p95_bytes", True)} MiB; '
          f'mean scenario CPU={value("scenario_cpu_mean_percent")}%; '
          f'mean CPU/platform={value("platform_cpu_mean_percent")}%', flush=True)


def data_mac(index):
    return mac(index, 1)


def generate(directory, kind, count, image):
    validate_count(count)
    directory.mkdir(parents=True, exist_ok=True)
    host_ip = addresses(0)[0]
    host_mac = mac(0, 3)
    hosts = [{'ID': 'h1', 'INTERFACES': [{'MAC': host_mac, 'IP': f'{host_ip}/{PREFIX_LENGTH}'}]}]
    connections = [{'IN/OUT': 'h1', 'IN/OUTIFACE': host_mac, 'OUT/IN': 's1'}]
    resources = []
    for i in range(count):
        ident = f'st-{kind}{i + 1:02d}'
        data_address = data_mac(i)
        endpoint_ip = addresses(i)[1]
        iface = {'ID': f'stb{i:02d}', 'MAC': data_address, 'IP': f'{endpoint_ip}/{PREFIX_LENGTH}',
                 'LINK_MAC': mac(i, 4)}
        if kind == 'vm':
            iface.pop('IP')  # Guest derives its shared-LAN address from the data MAC at boot.
            spec = {'ID': ident, 'MEMORY': 256, 'VCPU': 1, 'DISK': 'alpine-http',
                    'MANAGEMENT_MAC': mac(i, 2),
                    'INTERFACES': [iface]}
        else:
            spec = {'ID': ident, 'IMAGE': image, 'COMMAND': [
                '/bin/busybox-extras', 'httpd', '-f', '-p', '8080', '-h', '/var/www'],
                'PRIVILEGED': False, 'INTERFACES': [iface]}
        filename = f'{ident}.json'
        (directory / filename).write_text(json.dumps(spec, indent=2) + '\n')
        resources.append(filename)
        connections.append({'IN/OUT': 's1',
                            'OUT/IN': ident, 'OUT/INIFACE': data_address})
    topology = {'ID': f'Startup{kind}{count}', 'VMS': resources if kind == 'vm' else [],
                'CONTAINERS': resources if kind == 'container' else [], 'VNFS': [], 'SFCS': [],
                'MININET': {'HOSTS': hosts, 'SWITCHES': ['s1'], 'CONTROLLERS': [], 'OVSWITCHES': []},
                'CONNECTIONS': connections}
    path = directory / 'topology.json'
    path.write_text(json.dumps(topology, indent=2) + '\n')
    return path, [f'st-{kind}{i + 1:02d}' for i in range(count)]


class Client:
    def __init__(self, executable, socket, rpc_timeout=600):
        self.command = [executable, '--socket', socket, '--json']
        self.env = dict(os.environ, NIEP_CLIENT_TIMEOUT=str(rpc_timeout))
        self.socket_path = socket
        self.stats_timeout = min(rpc_timeout, 10)

    def stats(self):
        # The protocol frame ends at newline. Do not wait for server EOF/audit
        # completion after the metrics reply has already arrived.
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.stats_timeout)
            connection.connect(self.socket_path)
            connection.sendall((json.dumps({'command': 'stats', 'args': []}) + '\n').encode())
            connection.shutdown(socket.SHUT_WR)
            buffer = bytearray()
            deadline = time.monotonic() + self.stats_timeout
            while b'\n' not in buffer:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('Resource stats timed out')
                connection.settimeout(remaining)
                chunk = connection.recv(4096)
                if not chunk:
                    raise RuntimeError('Incomplete resource stats response')
                buffer.extend(chunk)
                if len(buffer) > 65536:
                    raise RuntimeError('Resource stats response exceeds protocol limit')
            frame, _, trailing = buffer.partition(b'\n')
            if trailing:
                raise RuntimeError('Unexpected data after stats response')
            response = json.loads(frame)
            if not response.get('ok'):
                raise RuntimeError(json.dumps(response))
            return response['data']

    def call(self, *args):
        if args == ('stats',):
            return self.stats()
        result = subprocess.run(self.command + list(args), capture_output=True, text=True,
                                env=self.env)
        try:
            response = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(result.stderr or result.stdout or 'Empty daemon response') from exc
        if result.returncode or not response.get('ok'):
            raise RuntimeError(json.dumps(response))
        return response.get('data')


def runtime_rows(client, capture_id, instances, kind, count, repeat, *, wait, timeout):
    deadline = time.monotonic() + timeout
    while True:
        snapshot = client.call('startup-timing', 'snapshot')
        if snapshot.get('capture_id') != capture_id:
            raise RuntimeError('Startup timing capture changed during the trial')
        records = {(row['kind'], row['id']): row for row in snapshot['resources']}
        pending = any(records.get((kind, ident), {}).get('status') == 'pending' for ident in instances)
        if not wait or not pending or time.monotonic() >= deadline:
            break
        time.sleep(.1)
    final = client.call('startup-timing', 'disable')
    if final.get('capture_id') != capture_id:
        raise RuntimeError('Startup timing capture changed while stopping probes')
    records = {(row['kind'], row['id']): row for row in final['resources']}
    rows = []
    for ident in instances:
        source = records.get((kind, ident), {})
        row = dict.fromkeys(RUNTIME_FIELDS, '')
        row.update({key: source[key] for key in RUNTIME_FIELDS if key in source})
        row.update(kind=kind, count=count, repeat=repeat, instance=ident)
        if not source:
            row.update(status='not_started', error='No runtime start event was recorded')
        rows.append(row)
    return rows


def trial(client, path, instances, kind, count, repeat, timeout, interval, *,
          observe_seconds=0, stats_interval=1, settle_seconds=2, save_samples=lambda rows: None,
          capture_runtime=False, save_runtime=lambda rows: None):
    rows = [dict.fromkeys(STARTUP_FIELDS, '') for _ in instances]
    for row, ident in zip(rows, instances):
        row.update(kind=kind, count=count, repeat=repeat, instance=ident, status='failed')
    defined = False
    cleanup_errors = []
    interrupted = False
    capture_id = None
    try:
        before = time.perf_counter()
        client.call('define', str(path))
        defined = True
        define_ms = (time.perf_counter() - before) * 1000
        if capture_runtime:
            capture_id = client.call('startup-timing', 'arm', str(timeout), '0.1')['capture_id']
        start = time.perf_counter()
        client.call('topoup')
        topoup_ms = (time.perf_counter() - start) * 1000
        for row in rows:
            row.update(define_ms=round(define_ms, 3), topoup_ms=round(topoup_ms, 3))
        pending = set(range(count))
        # A common deadline from before topoup; one bounded probe per pending host per round.
        deadline = start + timeout
        while pending and time.perf_counter() < deadline:
            for i in sorted(pending):
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    break
                endpoint_ip = addresses(i)[1]
                response = client.call('mininet', 'cmd', 'h1', 'curl',
                                       '--noproxy', endpoint_ip, '--silent', '--show-error',
                                       '--max-time', str(min(0.3, remaining)), '--write-out',
                                       '%{http_code}', f'http://{endpoint_ip}:8080/health')
                output = response.get('output', '')
                rows[i]['error'] = output.strip()
                if output.strip() == 'ok200':
                    rows[i].update(ready_ms=round((time.perf_counter() - start) * 1000, 3),
                                   status='ready', error='')
                    pending.remove(i)
            if pending:
                time.sleep(min(interval, max(0, deadline - time.perf_counter())))
        all_ready = max(row['ready_ms'] for row in rows) if not pending else ''
        for row in rows:
            row['all_ready_ms'] = all_ready
            if row['status'] != 'ready':
                row.update(status='timeout', error=f'HTTP timeout after {timeout}s: {row["error"]}')
        if not pending and observe_seconds > 0:
            samples = observe(client, instances, kind, count, repeat, duration=observe_seconds,
                              interval=stats_interval, settle=settle_seconds, save=save_samples)
            summary = summarize(samples, count)
            for row in rows:
                if any(sample['status'] != 'sampled' for sample in samples):
                    row.update(status='metrics_failed', error='Incomplete resource samples; see usage rows')
            print_summary(kind, count, repeat, summary)
    except KeyboardInterrupt:
        interrupted = True
        for row in rows:
            if observe_seconds > 0 or row['status'] != 'ready':
                row.update(status='interrupted', error='Interrupted by user')
    except Exception as exc:
        for row in rows:
            if row['status'] == 'ready':
                row['status'] = 'metrics_failed'
            row['error'] = str(exc)
    finally:
        try:
            if capture_id is not None:
                try:
                    save_runtime(runtime_rows(client, capture_id, instances, kind, count, repeat,
                                              wait=not interrupted and all(r['status'] == 'ready' for r in rows),
                                              timeout=timeout))
                except Exception as exc:
                    failures = [dict.fromkeys(RUNTIME_FIELDS, '') for _ in instances]
                    for row, ident in zip(failures, instances):
                        row.update(kind=kind, count=count, repeat=repeat, instance=ident,
                                   status='collection_failed', error=str(exc))
                    save_runtime(failures)
        finally:
            if defined:
                # Always attempt destroy even if stop fails. Never continue after uncertain cleanup.
                for command in ('topodown', 'topodestroy'):
                    try:
                        client.call(command)
                    except Exception as exc:
                        cleanup_errors.append(f'{command}: {exc}')
    if cleanup_errors:
        for row in rows:
            row.update(status='cleanup_failed', error=(row['error'] + '; ' if row['error'] else '') +
                       '; '.join(cleanup_errors))
    return rows, bool(cleanup_errors) or interrupted


@contextmanager
def results_files(directory, runtime_timing=False):
    """Append to raw-data CSVs under one output-directory lock."""
    schemas = {name: fields for name, fields in SCHEMAS.items()
               if runtime_timing or name != 'runtime_startup'}
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            fcntl.flock(directory_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'Another benchmark is writing {directory}') from exc
        # Validate all headers before changing any files.
        for name, fields in schemas.items():
            path = directory / f'{name}.csv'
            if path.exists() and path.stat().st_size:
                with path.open(newline='') as source:
                    header = next(csv.reader(source), None)
                    if header != list(fields):
                        raise RuntimeError(f'Incompatible CSV header in {path}; choose another --output')
        with ExitStack() as stack:
            files = {}
            for name, fields in schemas.items():
                handle = stack.enter_context((directory / f'{name}.csv').open('a+', newline=''))
                handle.seek(0, os.SEEK_END)
                writer = csv.DictWriter(handle, fieldnames=fields)
                if not handle.tell():
                    writer.writeheader()
                    handle.flush()
                files[name] = (writer, handle)
            yield files
    finally:
        os.close(directory_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts', nargs='+', type=positive_count, default=list(COUNTS))
    parser.add_argument('--kinds', nargs='+', choices=('vm', 'container'), default=['vm', 'container'])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=180,
                        help='HTTP deadline in seconds from before topoup (default: 180)')
    parser.add_argument('--rpc-timeout', type=float, default=600,
                        help='Daemon command timeout, including startup/cleanup (default: 600s)')
    parser.add_argument('--observe-seconds', type=float, default=10,
                        help='Resource observation window after settling (default: 10 seconds)')
    parser.add_argument('--stats-interval', type=float, default=1,
                        help='Resource polling interval (default: 1 second)')
    parser.add_argument('--settle-seconds', type=float, default=2,
                        help='Wait after all instances answer HTTP (default: 2 seconds)')
    parser.add_argument('--interval', type=float, default=0.1, help='HTTP readiness poll delay')
    parser.add_argument('--socket', default=os.environ.get('NIEP_SOCKET', '/run/niep.sock'))
    parser.add_argument('--image', default='niep-bench-http:alpine3.20')
    parser.add_argument('--output', type=Path, default=Path('benchmarks/startup/output'),
                        help='Shared directory for startup.csv, usage.csv and runtime_startup.csv (append on each run)')
    parser.add_argument('--skip-runtime-timing', action='store_true',
                        help='Disable per-instance runtime startup probes (enabled by default)')
    parser.add_argument('--generate-only', action='store_true')
    parser.add_argument('--keep-going', action='store_true',
                        help='Continue after a failed trial (cleanup failures always stop)')
    parser.add_argument('--vm-image', type=Path, default=Path(
        os.environ.get('NIEP_ROOT', Path(__file__).resolve().parents[2])) /
        'VEM/IMAGES/alpine-http.qcow2', help='Base image used by the daemon, for offline preflight')
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0 or args.interval < 0 or args.rpc_timeout <= 0:
        parser.error('repeats and timeout must be positive; interval must be nonnegative')
    if (not all(math.isfinite(v) for v in (args.observe_seconds, args.stats_interval, args.settle_seconds))
            or args.stats_interval <= 0 or args.observe_seconds < args.stats_interval
            or args.settle_seconds < 0):
        parser.error('observation duration must cover one positive stats interval; settle must be nonnegative')
    try:
        for count in args.counts:
            validate_count(count)
    except ValueError as exc:
        parser.error(str(exc))
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    # Temporary descriptors remain available to the daemon until all trials finish.
    with tempfile.TemporaryDirectory(prefix='niep-startup-') as work:
        directory = args.output / 'topologies' if args.generate_only else Path(work)
        plans = [(kind, count, *generate(directory / kind / str(count), kind, count, args.image))
                 for kind in args.kinds for count in args.counts]
        if args.generate_only:
            print(f'Topologies: {directory}', flush=True)
            return 0
        with results_files(args.output, runtime_timing=not args.skip_runtime_timing) as files:
            print('Results: ' + ', '.join(str(args.output / f'{name}.csv') for name in files), flush=True)
            return execute(args, plans, files)


def execute(args, plans, files):
    run_id = uuid4().hex
    metadata = dict(run_id=run_id)
    executable = Path(sys.executable).with_name('niepctl')
    client = Client(str(executable) if executable.is_file() else shutil.which('niepctl') or 'niepctl',
                    args.socket, args.rpc_timeout)
    if client.call('status')['defined']:
        raise RuntimeError('Daemon already has a topology; stop this run without changing it')
    try:
        if 'resources' not in client.call('stats'):
            raise RuntimeError('Invalid stats response')
    except RuntimeError as exc:
        raise RuntimeError('Resource stats unavailable; restart the updated niepd. ' + str(exc)) from exc
    if not args.skip_runtime_timing:
        try:
            client.call('startup-timing', 'snapshot')
        except RuntimeError as exc:
            raise RuntimeError('Restart updated niepd for integrated startup timing, or use --skip-runtime-timing') from exc
    if 'vm' in args.kinds:
        subprocess.run([sys.executable, str(Path(__file__).with_name('prepare-image.py')),
                        str(args.vm_image), '--count', str(max(args.counts))], check=True)
    if 'container' in args.kinds:
        # Resolve locally before timing: daemon must never pull during a trial.
        subprocess.run(['docker', 'image', 'inspect', args.image],
                       capture_output=True, text=True, check=True)
    def save(name, rows):
        writer, handle = files[name]
        for row in rows:
            combined = dict(row, **metadata)
            writer.writerow({key: combined.get(key, '') for key in SCHEMAS[name]})
        handle.flush()

    failed = False
    for kind, count, path, instances in plans:
        for repeat in range(1, args.repeats + 1):
            metadata['scenario_id'] = uuid4().hex
            started_at = datetime.now(timezone.utc).isoformat()
            runtime_records = []

            def save_runtime(records):
                runtime_records.extend(records)
                save('runtime_startup', records)

            rows, cleanup_failed = trial(client, path, instances, kind, count, repeat,
                                          args.timeout, args.interval,
                                          observe_seconds=args.observe_seconds, stats_interval=args.stats_interval,
                                          settle_seconds=args.settle_seconds,
                                          save_samples=lambda rows: save('usage', rows),
                                          capture_runtime=not args.skip_runtime_timing, save_runtime=save_runtime)
            for row in rows:
                row['started_at'] = started_at
            save('startup', rows)
            success = all(row['status'] == 'ready' for row in rows)
            timing_failed = any(row['status'] != 'ready' for row in runtime_records)
            if timing_failed:
                print('Runtime startup timing incomplete; see runtime_startup.csv', file=sys.stderr)
            failed |= timing_failed
            failed |= not success
            print(f'{kind} n={count} repeat={repeat}: '
                  f'{rows[0]["all_ready_ms"]} ms' if success else
                  f'{kind} n={count} repeat={repeat}: FAILED (see startup.csv and usage.csv)', flush=True)
            if not success:
                for row in rows:
                    if row['error']:
                        print(f"{row['instance']}: {row['error']}", file=sys.stderr)
            if any(row['status'] == 'interrupted' for row in rows):
                print('Interrupted; partial results saved and cleanup attempted.', file=sys.stderr)
                return 130
            if cleanup_failed or ((not success or timing_failed) and not args.keep_going):
                return 1
    return int(failed)


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1)
