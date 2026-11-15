#!/usr/bin/env python3
"""Measure NIEP topology startup through HTTP on independent Mininet links."""
import argparse
import csv
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tempfile
from uuid import uuid4
from datetime import datetime, timezone


COUNTS = (1, 2, 4, 8, 16)
FIELDS = ('run_id', 'started_at', 'config_json', 'image_id', 'kind', 'count', 'repeat', 'instance', 'ready_ms', 'all_ready_ms',
          'define_ms', 'topoup_ms', 'status', 'error')


def data_mac(index):
    return f'52:54:02:20:{16 + index:02x}:01'


def generate(directory, kind, count, image):
    directory.mkdir(parents=True, exist_ok=True)
    hosts, connections, resources = [], [], []
    for i in range(count):
        ident = f'st-{kind}{i + 1:02d}'
        host = f'h{i + 1}'
        mac = data_mac(i)
        host_mac = f'02:00:00:20:{16 + i:02x}:11'
        iface = {'ID': f'stb{i:02d}', 'MAC': mac, 'IP': '10.20.0.2/24',
                 'LINK_MAC': f'02:00:00:20:{16 + i:02x}:fe'}
        if kind == 'vm':
            iface.pop('IP')  # Address configured at guest boot by network-map.
            spec = {'ID': ident, 'MEMORY': 256, 'VCPU': 1, 'DISK': 'alpine-http',
                    'MANAGEMENT_MAC': f'52:54:02:20:{16 + i:02x}:00',
                    'INTERFACES': [iface]}
        else:
            spec = {'ID': ident, 'IMAGE': image, 'COMMAND': [
                '/bin/busybox-extras', 'httpd', '-f', '-p', '8080', '-h', '/var/www'],
                'PRIVILEGED': False, 'INTERFACES': [iface]}
        filename = f'{ident}.json'
        (directory / filename).write_text(json.dumps(spec, indent=2) + '\n')
        resources.append(filename)
        hosts.append({'ID': host, 'INTERFACES': [{'MAC': host_mac, 'IP': '10.20.0.1/24'}]})
        connections.append({'IN/OUT': host, 'IN/OUTIFACE': host_mac,
                            'OUT/IN': ident, 'OUT/INIFACE': mac})
    topology = {'ID': f'Startup{kind}{count}', 'VMS': resources if kind == 'vm' else [],
                'CONTAINERS': resources if kind == 'container' else [], 'VNFS': [], 'SFCS': [],
                'MININET': {'HOSTS': hosts, 'SWITCHES': [], 'CONTROLLERS': [], 'OVSWITCHES': []},
                'CONNECTIONS': connections}
    path = directory / 'topology.json'
    path.write_text(json.dumps(topology, indent=2) + '\n')
    return path, [f'st-{kind}{i + 1:02d}' for i in range(count)]


class Client:
    def __init__(self, executable, socket, rpc_timeout=600):
        self.command = [executable, '--socket', socket, '--json']
        self.env = dict(os.environ, NIEP_CLIENT_TIMEOUT=str(rpc_timeout))

    def call(self, *args):
        result = subprocess.run(self.command + list(args), capture_output=True, text=True,
                                env=self.env)
        try:
            response = json.loads(result.stdout)
        except ValueError as exc:
            raise RuntimeError(result.stderr or result.stdout or 'Empty daemon response') from exc
        if result.returncode or not response.get('ok'):
            raise RuntimeError(json.dumps(response))
        return response.get('data')


def trial(client, path, instances, kind, count, repeat, timeout, interval):
    rows = [dict.fromkeys(FIELDS, '') for _ in instances]
    for row, ident in zip(rows, instances):
        row.update(kind=kind, count=count, repeat=repeat, instance=ident, status='failed')
    defined = False
    cleanup_errors = []
    interrupted = False
    try:
        before = time.perf_counter()
        client.call('define', str(path))
        defined = True
        define_ms = (time.perf_counter() - before) * 1000
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
                response = client.call('mininet', 'cmd', f'h{i + 1}', 'curl',
                                       '--noproxy', '10.20.0.2', '--silent', '--show-error',
                                       '--max-time', str(min(0.3, remaining)), '--write-out',
                                       '%{http_code}', 'http://10.20.0.2:8080/health')
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
    except KeyboardInterrupt:
        interrupted = True
        for row in rows:
            if row['status'] != 'ready':
                row.update(status='interrupted', error='Interrupted by user')
    except Exception as exc:
        for row in rows:
            if row['status'] != 'ready':
                row['error'] = str(exc)
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
def results_file(path):
    """Append to a compatible CSV while preventing concurrent writers."""
    with path.open('a+', newline='') as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f'Another benchmark is writing {path}') from exc
        handle.seek(0)
        header = next(csv.reader(handle), None)
        if header is not None and header != list(FIELDS):
            raise RuntimeError(f'Incompatible CSV header in {path}; choose another --output')
        handle.seek(0, os.SEEK_END)
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        if header is None:
            writer.writeheader()
            handle.flush()
        yield writer, handle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--counts', nargs='+', type=int, choices=COUNTS, default=list(COUNTS))
    parser.add_argument('--kinds', nargs='+', choices=('vm', 'container'), default=['vm', 'container'])
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--timeout', type=float, default=180,
                        help='HTTP deadline in seconds from before topoup (default: 180)')
    parser.add_argument('--rpc-timeout', type=float, default=600,
                        help='Daemon command timeout, including startup/cleanup (default: 600s)')
    parser.add_argument('--interval', type=float, default=0.1)
    parser.add_argument('--socket', default=os.environ.get('NIEP_SOCKET', '/run/niep.sock'))
    parser.add_argument('--image', default='niep-bench-http:alpine3.20')
    parser.add_argument('--output', type=Path, default=Path('benchmarks/startup/output'),
                        help='Shared results directory (results.csv is appended on each run)')
    parser.add_argument('--generate-only', action='store_true')
    parser.add_argument('--keep-going', action='store_true',
                        help='Continue after a failed trial (cleanup failures always stop)')
    parser.add_argument('--vm-image', type=Path, default=Path(
        os.environ.get('NIEP_ROOT', Path(__file__).resolve().parents[2])) /
        'VEM/IMAGES/alpine-http.qcow2', help='Base image used by the daemon, for offline preflight')
    args = parser.parse_args()
    if args.repeats < 1 or args.timeout <= 0 or args.interval < 0 or args.rpc_timeout <= 0:
        parser.error('repeats and timeout must be positive; interval must be nonnegative')
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
        with results_file(args.output / 'results.csv') as (writer, handle):
            print(f'Results: {args.output / "results.csv"}', flush=True)
            return execute(args, plans, writer, handle)


def execute(args, plans, writer, handle):
    run_id = uuid4().hex
    started_at = datetime.now(timezone.utc).isoformat()
    metadata = dict(run_id=run_id, started_at=started_at,
                    config_json=json.dumps(vars(args), default=str, sort_keys=True), image_id='')
    executable = Path(sys.executable).with_name('niepctl')
    client = Client(str(executable) if executable.is_file() else shutil.which('niepctl') or 'niepctl',
                    args.socket, args.rpc_timeout)
    if client.call('status')['defined']:
        raise RuntimeError('Daemon already has a topology; stop this run without changing it')
    if 'vm' in args.kinds:
        subprocess.run([sys.executable, str(Path(__file__).with_name('prepare-image.py')),
                        str(args.vm_image), '--count', str(max(args.counts))], check=True)
    if 'container' in args.kinds:
        # Resolve locally before timing: daemon must never pull during a trial.
        inspection = subprocess.run(['docker', 'image', 'inspect', args.image],
                                    capture_output=True, text=True, check=True)
        metadata['image_id'] = json.loads(inspection.stdout)[0]['Id']
    failed = False
    for kind, count, path, instances in plans:
        for repeat in range(1, args.repeats + 1):
            rows, cleanup_failed = trial(client, path, instances, kind, count, repeat,
                                          args.timeout, args.interval)
            for row in rows:
                row.update(metadata)
            writer.writerows(rows)
            handle.flush()
            success = all(row['status'] == 'ready' for row in rows)
            failed |= not success
            print(f'{kind} n={count} repeat={repeat}: '
                  f'{rows[0]["all_ready_ms"]} ms' if success else
                  f'{kind} n={count} repeat={repeat}: FAILED (see results.csv)', flush=True)
            if not success:
                for row in rows:
                    if row['error']:
                        print(f"{row['instance']}: {row['error']}", file=sys.stderr)
            if any(row['status'] == 'interrupted' for row in rows):
                print('Interrupted; partial results saved and cleanup attempted.', file=sys.stderr)
                return 130
            if cleanup_failed or (not success and not args.keep_going):
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
