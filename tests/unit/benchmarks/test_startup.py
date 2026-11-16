"""Benchmark integrity: distinct identities, HTTP evidence, and cleanup failures."""
import json
from pathlib import Path
import runpy
import shlex

import pytest


BENCH = runpy.run_path(str(Path(__file__).resolve().parents[3] / 'benchmarks/startup/run.py'))


@pytest.mark.parametrize('kind', ['vm', 'container'])
@pytest.mark.parametrize('count', [1, 2, 4, 8, 16, 64, 128, 256, 257, 512])
def test_generated_topologies_have_unique_interfaces(tmp_path, kind, count):
    path, instances = BENCH['generate'](tmp_path, kind, count, 'local:test')
    topology = json.loads(path.read_text())
    assert len(topology['CONNECTIONS']) == count + 1
    assert len(topology['MININET']['HOSTS']) == 1
    assert topology['MININET']['SWITCHES'] == ['s1']
    assert len(set(instances)) == count
    specs = [json.loads((tmp_path / f'{ident}.json').read_text()) for ident in instances]
    assert len({spec['INTERFACES'][0]['MAC'] for spec in specs}) == count
    assert len({spec['INTERFACES'][0]['ID'] for spec in specs}) == count
    if kind == 'vm':
        assert len({spec['MANAGEMENT_MAC'] for spec in specs}) == count


class Client:
    def __init__(self, output='ok200', fail=None):
        self.output, self.fail, self.calls = output, fail, []

    def call(self, *args):
        self.calls.append(args[0])
        if args[0] == self.fail:
            raise RuntimeError('injected failure')
        if args[0] == 'disk-usage':
            return dict(timestamp='now', resources=[
                dict(kind=kind, id=ident, disk_bytes=1024, error=None,
                     image_id='sha256:shared', image_bytes=8192, image_source='docker_image_size',
                     source='host_allocated_blocks' if kind == 'vm' else 'docker_writable_layer')
                for kind, ident in [('vm', 'vm1'), ('vm', 'vm2'),
                                    ('container', 'st-container01'), ('container', 'c1')]])
        if args[0] == 'mininet':
            command = shlex.split(args[3])
            return {'output': json.dumps([
                dict(index=i, ready_ms=(i + 1) * .1 if self.output == 'ok200' else '',
                     status='ready' if self.output == 'ok200' else 'timeout',
                     error='' if self.output == 'ok200' else self.output)
                for i in range(int(command[2]))])}
        return {'output': self.output}


def test_http_success_and_cleanup(tmp_path):
    client = Client()
    rows, failed = BENCH['trial'](client, tmp_path, ['vm1', 'vm2'], 'vm', 2, 1, 1, 0)
    assert not failed
    assert all(row['status'] == 'ready' for row in rows)
    assert rows[0]['all_ready_ms'] == rows[1]['ready_ms']
    assert client.calls[-2:] == ['topodown', 'topodestroy']


def test_wrong_http_body_times_out(tmp_path):
    client = Client(output='wrong200')
    rows, _ = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 0.001, 0)
    assert rows[0]['status'] == 'timeout'
    assert rows[0]['ready_ms'] == ''
    assert client.calls[-1] == 'topodestroy'


@pytest.mark.parametrize('operation', ['topoup', 'topodown'])
def test_cleanup_attempts_destroy_after_failure(tmp_path, operation):
    client = Client(fail=operation)
    rows, failed = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0)
    assert client.calls[-1] == 'topodestroy'
    assert failed == (operation == 'topodown')
    assert rows[0]['status'] != 'ready'


@pytest.mark.parametrize('failure', [None, 'topodown', 'topoup', 'define'])
def test_topodown_timing_excludes_destroy_and_is_kept_after_failures(tmp_path, monkeypatch, failure):
    elapsed = [0.0]
    module = BENCH['trial'].__globals__
    monkeypatch.setattr(module['time'], 'perf_counter', lambda: elapsed[0])

    class TimedClient(Client):
        def call(self, *args):
            elapsed[0] += {'topodown': 2.75, 'topodestroy': 30, 'disk-usage': 4}.get(args[0], .1)
            return super().call(*args)

    client = TimedClient(fail=failure)
    rows, stop = BENCH['trial'](client, tmp_path, ['vm1', 'vm2'], 'vm', 2, 1, 100, 0)
    if failure == 'define':
        assert all(row['topodown_ms'] == '' for row in rows)
        assert 'topodown' not in client.calls
    else:
        assert all(row['topodown_ms'] == 2750.0 for row in rows)
        assert client.calls[-2:] == ['topodown', 'topodestroy']
    if failure == 'topodown':
        assert stop and all(row['status'] == 'cleanup_failed' for row in rows)


def test_interrupt_saves_partial_observations_and_cleans(tmp_path):
    markers = []

    class InterruptedClient(Client):
        def call(self, *args):
            if args[0] == 'mininet':
                marker = Path(shlex.split(args[3])[-1])
                assert marker.exists()
                markers.append(marker)
                raise KeyboardInterrupt
            return super().call(*args)

    client = InterruptedClient()
    rows, stop = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0)
    assert stop
    assert rows[0]['status'] == 'interrupted'
    assert client.calls[-2:] == ['topodown', 'topodestroy']
    assert markers and not markers[0].exists()


@pytest.mark.parametrize('output', ['not JSON', '[]',
                                  '[{"index":0,"status":"ready","ready_ms":NaN,"error":""}]'])
def test_invalid_collector_results_fail_and_cleanup(tmp_path, output):
    class InvalidClient(Client):
        def call(self, *args):
            if args[0] == 'mininet':
                self.calls.append('mininet')
                return {'output': output}
            return super().call(*args)

    client = InvalidClient()
    rows, _ = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0)
    assert rows[0]['status'] == 'failed'
    assert rows[0]['ready_ms'] == ''
    assert rows[0]['error']
    assert client.calls[-2:] == ['topodown', 'topodestroy']


@pytest.mark.parametrize('count, passes', [(1, False), (64, True), (257, True)])
def test_image_preflight_requires_procedural_guest_support(tmp_path, monkeypatch, count, passes):
    helper = runpy.run_path(str(Path(__file__).resolve().parents[3] /
                               'benchmarks/startup/prepare-image.py'))
    source = tmp_path / 'base.qcow2'
    source.write_bytes(b'original')

    def fake_command(*args):
        if args[0] == 'qemu-img':
            Path(args[-1]).write_bytes(b'root')
            return ''
        if args[0] == 'sfdisk':
            return json.dumps({'partitiontable': {'sectorsize': 1, 'partitions': [
                {'type': '83', 'start': 0, 'size': 4}]}})
        if args[0] == 'debugfs':
            return helper['NETWORK'].read_text() if passes else '# old network service\n'
        raise AssertionError(args)

    monkeypatch.setitem(helper['process'].__globals__, 'command', fake_command)
    if passes:
        helper['process'](source, count=count)
    else:
        with pytest.raises(RuntimeError, match='lacks current procedural startup addressing'):
            helper['process'](source, count=count)
    assert source.read_bytes() == b'original'


def test_repeated_runs_append_joinable_raw_csvs(tmp_path, monkeypatch):
    import csv
    import sys
    from types import SimpleNamespace

    class IdleClient(Client):
        def call(self, *args):
            if args[0] == 'status':
                return {'defined': False}
            if args[0] == 'stats':
                return {'resources': []}
            return super().call(*args)

    def observe(_client, instances, kind, count, repeat, **kwargs):
        rows = [dict(kind=kind, count=count, repeat=repeat, instance=instances[0],
                     sample_index=1, sample_timestamp='now', elapsed_seconds=1,
                     memory_bytes=100, cpu_percent=20, status='sampled', error='')]
        kwargs['save'](rows)
        return rows

    module = BENCH['main'].__globals__
    monkeypatch.setitem(module, 'Client', lambda *_args: IdleClient())
    monkeypatch.setitem(module, 'observe', observe)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(stdout='[{"Id":"sha256:test"}]'))
    monkeypatch.setattr(sys, 'argv', ['run.py', '--kinds', 'container', '--counts', '1',
                                    '--repeats', '1', '--skip-runtime-timing', '--output', str(tmp_path)])
    assert BENCH['main']() == 0
    originals = {name: (tmp_path / f'{name}.csv').read_bytes() for name in ('startup', 'usage')}
    assert BENCH['main']() == 0
    tables = {}
    for name in originals:
        path = tmp_path / f'{name}.csv'
        assert path.read_bytes().startswith(originals[name])
        with path.open(newline='') as handle:
            tables[name] = list(csv.DictReader(handle))
        assert len(tables[name]) == 2
        assert tables[name][0]['run_id'] != tables[name][1]['run_id']
        assert 'config_json' not in tables[name][0]
        assert not any('mean' in key or 'p95' in key for key in tables[name][0])
        assert all(row['kind'] == 'container' and row['count'] == '1' for row in tables[name])
    for startup, usage in zip(tables['startup'], tables['usage']):
        assert all(startup[key] == usage[key] for key in BENCH['COMMON_FIELDS'])
        assert float(startup['topodown_ms']) >= 0
    assert tables['startup'][0]['scenario_id'] != tables['startup'][1]['scenario_id']
    with (tmp_path / 'host_memory.csv').open(newline='') as handle:
        host_rows = list(csv.DictReader(handle))
    assert len(host_rows) == 4
    for index, startup_row in enumerate(tables['startup']):
        pair = host_rows[2 * index:2 * index + 2]
        assert [r['phase'] for r in pair] == ['before_topoup', 'before_topodown']
        assert all(all(r[key] == startup_row[key] for key in
                       ('run_id', 'scenario_id', 'kind', 'count', 'repeat')) for r in pair)
        assert all(r['status'] == 'sampled' and int(r['mem_total_bytes']) > 0 for r in pair)
        assert all('delta' not in key and 'used' not in key for key in pair[0])
    with (tmp_path / 'disk_usage.csv').open(newline='') as handle:
        disk = list(csv.DictReader(handle))
    assert len(disk) == 2
    for row, startup_row in zip(disk, tables['startup']):
        assert all(row[key] == startup_row[key] for key in BENCH['COMMON_FIELDS'])
        assert row['disk_bytes'] == '1024' and row['source'] == 'docker_writable_layer'
        assert row['image_id'] == 'sha256:shared' and row['image_bytes'] == '8192'
        assert not row['image_error']
    assert {p.name for p in tmp_path.iterdir()} == {'startup.csv', 'usage.csv', 'host_memory.csv', 'disk_usage.csv'}


def test_csv_with_incompatible_header_is_preserved(tmp_path):
    path = tmp_path / 'usage.csv'
    original = 'old,header\n1,2\n'
    path.write_text(original)
    with pytest.raises(RuntimeError, match='Incompatible CSV header'):
        with BENCH['results_files'](tmp_path):
            pytest.fail('incompatible CSV must not be opened for writing')
    assert path.read_text() == original
    assert not (tmp_path / 'startup.csv').exists()


def test_csv_rejects_concurrent_writer(tmp_path):
    with BENCH['results_files'](tmp_path):
        with pytest.raises(RuntimeError, match='Another benchmark'):
            with BENCH['results_files'](tmp_path):
                pytest.fail('second writer must not acquire the directory lock')


def test_observation_waits_for_settle_seeds_cpu_then_polls_for_ten_seconds(monkeypatch):
    clock = [0.0]
    events = []
    saved = []
    module = BENCH['observe'].__globals__
    monkeypatch.setattr(module['time'], 'monotonic', lambda: clock[0])

    def sleep(seconds):
        clock[0] += seconds

    monkeypatch.setattr(module['time'], 'sleep', sleep)

    class StatsClient:
        def call(self, command):
            assert command == 'stats'
            events.append(clock[0])
            return {'timestamp': str(clock[0]), 'resources': [
                {'kind': 'vm', 'id': ident, 'state': 'running',
                 'memory_bytes': memory, 'cpu_percent': cpu}
                for ident, memory, cpu in [('vm1', 100, 20), ('vm2', 300, 40)]]}

    samples = BENCH['observe'](StatsClient(), ['vm1', 'vm2'], 'vm', 2, 1,
                               duration=10, interval=1, settle=2, save=saved.extend)
    assert events == list(range(2, 13))  # baseline at 2; observations at 3..12
    assert len(saved) == len(samples) == 20
    assert samples[0]['elapsed_seconds'] == 1
    assert samples[-1]['elapsed_seconds'] == 10
    summary = BENCH['summarize'](samples, 2)
    assert summary == dict(scenario_memory_mean_bytes=400, platform_memory_mean_bytes=200,
                           platform_memory_p95_bytes=300, scenario_cpu_mean_percent=60,
                           platform_cpu_mean_percent=30)


def test_legacy_results_are_preserved(tmp_path):
    path = tmp_path / 'results.csv'
    original = 'old,results\n123,456\n'
    path.write_text(original)
    with BENCH['results_files'](tmp_path):
        pass
    assert path.read_text() == original


def test_partial_observation_does_not_report_incomplete_totals_as_complete():
    samples = [dict(sample_index=1, memory_bytes=100, cpu_percent=None),
               dict(sample_index=1, memory_bytes=None, cpu_percent=20)]
    summary = BENCH['summarize'](samples, 2)
    assert summary['scenario_memory_mean_bytes'] is None
    assert summary['scenario_cpu_mean_percent'] is None
    assert summary['platform_memory_mean_bytes'] == 100


def test_resource_collection_finishes_before_topology_cleanup(tmp_path, monkeypatch, capsys):
    client = Client()

    def observe(_client, instances, kind, count, repeat, **kwargs):
        assert client.calls[-1] == 'mininet'
        assert 'topodown' not in client.calls
        assert kwargs['settle'] == 2
        assert kwargs['duration'] == 10
        assert kwargs['interval'] == 1
        return [dict(sample_index=1, memory_bytes=100, cpu_percent=25, status='sampled')]

    monkeypatch.setitem(BENCH['trial'].__globals__, 'observe', observe)
    rows, failed = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0,
                                  observe_seconds=10)
    assert not failed
    assert 'scenario_memory_mean_bytes' not in rows[0]
    output = capsys.readouterr().out
    assert 'mean scenario memory=' in output
    assert 'p95 memory/platform=' in output
    assert client.calls[-2:] == ['topodown', 'topodestroy']


@pytest.mark.parametrize('count', [0, 512])
def test_stats_reads_a_complete_frame_without_waiting_for_server_close(tmp_path, count):
    import socket
    import threading

    path = str(tmp_path / 'stats.sock')
    release = threading.Event()
    resources = [dict(kind='container', id=f'c{i}', state='running', memory_bytes=12345,
                      cpu_percent=0.1, timestamp='2026-11-16T00:00:00Z', error=None)
                 for i in range(count)]
    frame = (json.dumps({'ok': True, 'data': {'resources': resources}}) + '\n').encode()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(path)
        listener.listen()

        def serve():
            with listener.accept()[0] as connection:
                connection.recv(4096)
                connection.sendall(frame)
                release.wait(2)

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            client = BENCH['Client']('unused', path, rpc_timeout=1)
            assert client.call('stats') == {'resources': resources}
        finally:
            release.set()
            thread.join(timeout=3)


@pytest.mark.parametrize('value', ['0', '-1', '1.5', 'text'])
def test_counts_reject_non_positive_integers(value):
    from niep.domain.startup_addressing import positive_count
    with pytest.raises(ValueError):
        positive_count(value)


@pytest.mark.parametrize('index', [0, 1, 63, 239, 240, 255, 256, 65536, (1 << 22) - 1, (1 << 24) - 4])
def test_guest_procedural_address_matches_topology(index):
    import subprocess
    from niep.domain.startup_addressing import addresses, mac
    guest = Path(__file__).resolve().parents[3] / 'benchmarks/images/alpine-http/guest/network'
    function = guest.read_text().split('start() {')[0]
    # Exercise the actual POSIX guest implementation, including octet carries.
    result = subprocess.run(['sh', '-c', function + '\nstartup_address "$1"',
                             'test', mac(index, 1)], text=True, capture_output=True, check=True)
    assert result.stdout == addresses(index)[1] + '/8'
    assert len(mac(index, 1).split(':')) == 6
    assert mac(index, 1) != mac(index, 2)


def test_generated_addresses_are_unique_across_a_large_scenario(tmp_path):
    from niep.domain.startup_addressing import addresses
    path, instances = BENCH['generate'](tmp_path, 'container', 257, 'test:image')
    topology = json.loads(path.read_text())
    host_ips = {h['INTERFACES'][0]['IP'] for h in topology['MININET']['HOSTS']}
    endpoints = [json.loads((tmp_path / f'{ident}.json').read_text()) for ident in instances]
    endpoint_ips = {e['INTERFACES'][0]['IP'] for e in endpoints}
    assert len(host_ips) == 1
    assert len(endpoint_ips) == 257
    assert not host_ips & endpoint_ips
    assert len(host_ips | endpoint_ips) == 258
    assert endpoints[256]['INTERFACES'][0]['IP'] == addresses(256)[1] + '/8'


def test_shared_switch_probes_every_instance_from_the_same_host(tmp_path):
    from niep.domain.startup_addressing import addresses
    probes = []

    class ProbeClient(Client):
        def call(self, *args):
            if args[0] == 'mininet':
                probes.append(args)
            return super().call(*args)

    rows, failed = BENCH['trial'](ProbeClient(), tmp_path, ['vm1', 'vm2'], 'vm', 2, 1, 1, 0)
    assert not failed
    assert all(row['status'] == 'ready' for row in rows)
    assert len(probes) == 1
    assert probes[0][:3] == ('mininet', 'cmd', 'h1')
    command = shlex.split(probes[0][3])
    assert Path(command[1]).name == 'http-probe.py'
    assert command[2:4] == ['2', addresses(0)[1]]
    assert all(row['probe_method'] == 'mininet_parallel_http_v1' for row in rows)


def test_integrated_timing_creates_third_csv_for_same_instances(tmp_path, monkeypatch):
    import csv
    import sys
    from types import SimpleNamespace

    events = []
    resource = dict(kind='container', id='st-container01', runtime_id='docker-id',
                    started_at='now', start_call_ms=1, runtime_ready_ms=2,
                    probe_path='container_loopback', status='ready', error='')

    class IntegratedClient(Client):
        def call(self, *args):
            events.append(args)
            if args[0] == 'status':
                return {'defined': False}
            if args[0] == 'stats':
                return {'resources': []}
            if args[0] == 'startup-timing':
                return {'capture_id': 'capture', 'resources': [resource], 'pending': 0}
            return super().call(*args)

    def observe(_client, instances, kind, count, repeat, **kwargs):
        rows = [dict(kind=kind, count=count, repeat=repeat, instance=instances[0],
                     sample_index=1, sample_timestamp='now', elapsed_seconds=1,
                     memory_bytes=100, cpu_percent=20, status='sampled', error='')]
        kwargs['save'](rows)
        return rows

    module = BENCH['main'].__globals__
    monkeypatch.setitem(module, 'Client', lambda *_args: IntegratedClient())
    monkeypatch.setitem(module, 'observe', observe)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs: SimpleNamespace(stdout='[]'))
    monkeypatch.setattr(sys, 'argv', ['run.py', '--kinds', 'container', '--counts', '1',
                                    '--repeats', '1', '--output', str(tmp_path)])
    assert BENCH['main']() == 0
    tables = {}
    for name in ('startup', 'usage', 'runtime_startup'):
        with (tmp_path / f'{name}.csv').open() as handle:
            tables[name] = list(csv.DictReader(handle))
    runtime = tables['runtime_startup'][0]
    assert runtime['runtime_id'] == 'docker-id'
    assert runtime['runtime_ready_ms'] == '2'
    for name in ('startup', 'usage'):
        assert all(tables[name][0][key] == runtime[key] for key in BENCH['COMMON_FIELDS'])
    assert sum(event[0] == 'topoup' for event in events) == 2  # Warmup + measured trial.
    assert sum(event[0] == 'topodestroy' for event in events) == 2
    assert next(i for i, e in enumerate(events) if e[:2] == ('startup-timing', 'arm')) < next(
        i for i, e in enumerate(events) if e[0] == 'topoup')


def test_host_memory_snapshot_preserves_raw_counters_in_bytes(tmp_path):
    meminfo = tmp_path / 'meminfo'
    meminfo.write_text('MemTotal: 1024 kB\nMemAvailable: 700 kB\nMemFree: 500 kB\n'
                       'Buffers: 20 kB\nCached: 200 kB\nHugePages_Total: 0\n')
    row = BENCH['host_memory_snapshot']('before_topoup', 'vm', 64, 2, meminfo)
    assert row['status'] == 'sampled'
    assert row['mem_total_bytes'] == 1024 * 1024
    assert row['mem_available_bytes'] == 700 * 1024
    assert row['mem_free_bytes'] == 500 * 1024
    assert row['buffers_bytes'] == 20 * 1024
    assert row['cached_bytes'] == 200 * 1024
    assert row['sample_timestamp'].endswith('+00:00')
    assert not any('delta' in field or 'used' in field for field in row)


@pytest.mark.parametrize('text', [None, 'MemTotal: 100 kB\n',
                                 'MemTotal: 100 MB\n', 'MemTotal: -1 kB\n'])
def test_host_memory_snapshot_reports_unavailable_counters_without_zero_fallback(tmp_path, text):
    path = tmp_path / 'meminfo'
    if text is not None:
        path.write_text(text)
    row = BENCH['host_memory_snapshot']('before_topodown', 'container', 1, 1, path)
    assert row['status'] == 'metrics_error'
    assert row['error']
    assert row['mem_total_bytes'] == row['mem_available_bytes'] == ''


def test_host_snapshots_are_adjacent_to_start_stop_and_after_runtime_collection(tmp_path, monkeypatch):
    events, saved, saved_disk = [], [], []

    class OrderedClient(Client):
        def call(self, *args):
            events.append(args[:2] if args[0] == 'startup-timing' else args[:1])
            if args[0] == 'startup-timing':
                return dict(capture_id='capture', resources=[dict(kind='vm', id='vm1', status='ready')])
            return super().call(*args)

    def snapshot(phase, kind, count, repeat):
        events.append((phase,))
        return dict(phase=phase, kind=kind, count=count, repeat=repeat, status='sampled',
                    mem_total_bytes=1024, mem_available_bytes=800 if phase == 'before_topoup' else 700)

    def save_host(records):
        events.append(('save_host',))
        saved.extend(records)

    def observe(*_args, **_kwargs):
        events.append(('observe',))
        return [dict(sample_index=1, memory_bytes=100, cpu_percent=1, status='sampled')]

    monkeypatch.setitem(BENCH['trial'].__globals__, 'host_memory_snapshot', snapshot)
    monkeypatch.setitem(BENCH['trial'].__globals__, 'observe', observe)
    rows, failed = BENCH['trial'](OrderedClient(), tmp_path, ['vm1'], 'vm', 1, 1, 1, 0,
                                  capture_runtime=True, save_host_memory=save_host, observe_seconds=1,
                                  save_disk=saved_disk.extend)
    assert not failed and rows[0]['status'] == 'ready'
    assert events[events.index(('topoup',)) - 1] == ('before_topoup',)
    assert events[events.index(('topodown',)) - 1] == ('before_topodown',)
    assert events.index(('startup-timing', 'disable')) < events.index(('before_topodown',))
    assert events.index(('observe',)) < events.index(('before_topodown',))
    assert events.index(('startup-timing', 'disable')) < events.index(('disk-usage',))
    assert events.index(('disk-usage',)) < events.index(('before_topodown',))
    assert events.index(('topodestroy',)) < events.index(('save_host',))
    assert [row['phase'] for row in saved] == ['before_topoup', 'before_topodown']
    assert len(saved_disk) == 1 and saved_disk[0]['status'] == 'sampled'


@pytest.mark.parametrize('operation', ['define', 'topoup', 'topodown', 'mininet'])
def test_host_snapshots_on_lifecycle_failures(tmp_path, operation):
    saved = []
    client = Client(fail=operation)
    BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0, save_host_memory=saved.extend)
    assert [row['phase'] for row in saved] == ([] if operation == 'define' else
                                              ['before_topoup', 'before_topodown'])
    if operation != 'define':
        assert client.calls[-1] == 'topodestroy'


def test_host_memory_error_preserves_readiness_and_cleanup(tmp_path, monkeypatch):
    snapshot = BENCH['host_memory_snapshot']
    monkeypatch.setitem(BENCH['trial'].__globals__, 'host_memory_snapshot',
                        lambda *args: snapshot(*args, meminfo_path=tmp_path / 'missing'))
    client, saved = Client(), []
    rows, failed = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0,
                                  save_host_memory=saved.extend)
    assert not failed and rows[0]['status'] == 'ready'
    assert len(saved) == 2 and all(row['status'] == 'metrics_error' for row in saved)
    assert client.calls[-2:] == ['topodown', 'topodestroy']


def test_execute_reports_host_memory_failure_without_discarding_ready_startup(tmp_path, monkeypatch):
    import csv
    from types import SimpleNamespace

    class IdleClient(Client):
        def call(self, *args):
            if args[0] == 'status':
                return {'defined': False}
            if args[0] == 'stats':
                return {'resources': []}
            return super().call(*args)

    client = IdleClient()
    module = BENCH['execute'].__globals__
    snapshot = module['host_memory_snapshot']
    monkeypatch.setitem(module, 'host_memory_snapshot',
                        lambda *args: snapshot(*args, meminfo_path=tmp_path / 'missing'))
    monkeypatch.setitem(module, 'Client', lambda *_args: client)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs: None)
    args = SimpleNamespace(socket='unused', rpc_timeout=600, skip_runtime_timing=True,
                           kinds=['container'], image='local:test', repeats=1, timeout=1, seed=42,
                           interval=0, observe_seconds=0, stats_interval=1, settle_seconds=0,
                           keep_going=True)
    with BENCH['results_files'](tmp_path) as files:
        assert BENCH['execute'](args, [('container', 1, tmp_path, ['c1'])], files) == 1
    with (tmp_path / 'startup.csv').open() as source:
        assert list(csv.DictReader(source))[0]['status'] == 'ready'
    with (tmp_path / 'host_memory.csv').open() as source:
        snapshots = list(csv.DictReader(source))
        assert len(snapshots) == 2 and all(r['status'] == 'metrics_error' for r in snapshots)
    assert client.calls[-2:] == ['topodown', 'topodestroy']


def test_warmup_once_per_distinct_platform_size_is_excluded_from_all_csvs(tmp_path, monkeypatch, capsys):
    import csv
    from collections import Counter
    from types import SimpleNamespace

    events = []

    class IdleClient(Client):
        def call(self, *args):
            if args[0] == 'status':
                return {'defined': False}
            if args[0] in ('stats', 'startup-timing'):
                return {'resources': []}
            return super().call(*args)

    def trial(client, path, instances, kind, count, repeat, timeout, interval, **kwargs):
        events.append((kind, count, repeat))
        assert kwargs['report_summary'] == (repeat != 0)
        assert kwargs['capture_runtime']
        assert (kwargs['observe_seconds'], kwargs['stats_interval'], kwargs['settle_seconds']) == (10, 1, 2)
        common = dict(kind=kind, count=count, repeat=repeat)
        rows = [dict(common, instance=ident, status='ready', error='',
                     ready_ms=999999 if repeat == 0 else 100, all_ready_ms=100)
                for ident in instances]
        kwargs['save_samples']([dict(row, status='sampled', sample_index=1,
                                      memory_bytes=999999 if repeat == 0 else 100,
                                      cpu_percent=1) for row in rows])
        kwargs['save_runtime']([dict(row, start_call_ms=100, runtime_ready_ms=100) for row in rows])
        kwargs['save_host_memory']([dict(common, phase=phase, status='sampled',
                                         mem_total_bytes=1000, mem_available_bytes=900)
                                   for phase in ('before_topoup', 'before_topodown')])
        kwargs['save_disk']([dict(row, status='sampled', disk_bytes=999999 if repeat == 0 else 100,
                                 source='host_allocated_blocks' if kind == 'vm' else 'docker_writable_layer')
                            for row in rows])
        return rows, False

    module = BENCH['execute'].__globals__
    monkeypatch.setitem(module, 'Client', lambda *_args: IdleClient())
    monkeypatch.setitem(module, 'trial', trial)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs: None)
    args = SimpleNamespace(socket='unused', rpc_timeout=600, skip_runtime_timing=False,
                           kinds=['vm', 'container'], counts=[1, 2], vm_image=tmp_path,
                           image='local:test', repeats=2, timeout=180, interval=.1, seed=42,
                           observe_seconds=10, stats_interval=1, settle_seconds=2, keep_going=False)
    configurations = [('vm', 1), ('vm', 2), ('container', 1), ('container', 2), ('vm', 1)]
    plans = [(kind, count, tmp_path, [f'{kind}{i}' for i in range(count)])
             for kind, count in configurations]
    with BENCH['results_files'](tmp_path, runtime_timing=True) as files:
        assert BENCH['execute'](args, plans, files) == 0
    warmups = Counter((kind, count) for kind, count, repeat in events if repeat == 0)
    assert warmups == Counter({pair: 1 for pair in set(configurations)})
    assert [repeat for _, _, repeat in events if repeat] == [1] * 4 + [2] * 4
    for pair in set(configurations):
        sequence = [repeat for kind, count, repeat in events if (kind, count) == pair]
        assert sequence == [0, 1, 2]
    for name in BENCH['SCHEMAS']:
        with (tmp_path / f'{name}.csv').open() as source:
            rows = list(csv.DictReader(source))
        assert len(rows) == (16 if name == 'host_memory' else 12)
        assert {row['repeat'] for row in rows} == {'1', '2'}
        assert all('999999' not in row.values() for row in rows)
    assert capsys.readouterr().out.count('warmup: completed (results discarded)') == 4


@pytest.mark.parametrize('operation,keep_going,exit_code',
                         [('topoup', False, 1), ('topodown', True, 1), ('interrupt', True, 130)])
def test_failed_or_interrupted_warmup_cleans_and_leaves_csvs_empty(
        tmp_path, monkeypatch, operation, keep_going, exit_code):
    import csv
    from types import SimpleNamespace

    class WarmupClient(Client):
        def call(self, *args):
            if args[0] == 'status':
                return {'defined': False}
            if args[0] == 'stats':
                return {'resources': []}
            if args[0] == 'mininet' and operation == 'interrupt':
                raise KeyboardInterrupt
            return super().call(*args)

    client = WarmupClient(fail=operation)
    module = BENCH['execute'].__globals__
    monkeypatch.setitem(module, 'Client', lambda *_args: client)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs: None)
    args = SimpleNamespace(socket='unused', rpc_timeout=600, skip_runtime_timing=True,
                           kinds=['container'], image='local:test', repeats=2, timeout=1, seed=42,
                           interval=0, observe_seconds=0, stats_interval=1, settle_seconds=0,
                           keep_going=keep_going)
    with BENCH['results_files'](tmp_path) as files:
        assert BENCH['execute'](args, [('container', 1, tmp_path, ['c1'])], files) == exit_code
    assert client.calls.count('topoup') == client.calls.count('topodestroy') == 1
    assert client.calls[-2:] == ['topodown', 'topodestroy']
    for path in tmp_path.glob('*.csv'):
        with path.open() as source:
            assert list(csv.DictReader(source)) == []


def test_warmup_observes_resources_without_computing_or_printing_summary(tmp_path, monkeypatch):
    observed = []

    def observe(*args, **kwargs):
        observed.append(kwargs)
        return [dict(status='sampled')]

    def unexpected_summary(*args):
        pytest.fail('warmup must not contribute statistics')

    module = BENCH['trial'].__globals__
    monkeypatch.setitem(module, 'observe', observe)
    monkeypatch.setitem(module, 'summarize', unexpected_summary)
    monkeypatch.setitem(module, 'print_summary', unexpected_summary)
    rows, stop = BENCH['trial'](Client(), tmp_path, ['vm1'], 'vm', 1, 0, 1, 0,
                                observe_seconds=10, report_summary=False)
    assert not stop and rows[0]['status'] == 'ready'
    assert len(observed) == 1
    assert observed[0]['duration'] == 10


def test_randomized_rounds_match_requested_example_and_redraw_both_orders():
    plans = [(kind, count, Path(str(count)), [f'{kind}{count}'])
             for kind in ('vm', 'container') for count in (1, 2, 4, 8)]

    class ScriptedRandom:
        def __init__(self):
            self.draws = iter([[2, 1, 4, 8], ['container', 'vm'], ['vm', 'container'],
                               [8, 4, 1, 2], ['vm', 'container'], ['container', 'vm']])
            self.calls = 0

        def shuffle(self, values):
            self.calls += 1
            chosen = next(self.draws)
            assert set(chosen) == set(values)
            values[:] = chosen

    rng = ScriptedRandom()
    schedule = list(BENCH['experiment_schedule'](plans, 2, rng))
    tokens = [f'{count}{kind[0].upper()}' for _, (kind, count, _, _) in schedule]
    assert tokens[:8] == ['2C', '2V', '1V', '1C', '4V', '4C', '8C', '8V']
    assert tokens[8:] == ['8V', '8C', '4C', '4V', '1C', '1V', '2V', '2C']
    assert [repeat for repeat, _ in schedule] == [1] * 8 + [2] * 8
    assert rng.calls == 6
    assert all(plan in plans for _, plan in schedule)


@pytest.mark.parametrize('counts', [(1,), (1, 2), (1, 2, 4), (1, 2, 4, 8, 16, 32, 64)])
@pytest.mark.parametrize('kinds', [('vm',), ('container',), ('vm', 'container')])
def test_each_round_covers_every_configuration_once_with_balanced_first_platforms(counts, kinds):
    import random

    plans = [(kind, count, Path(str(count)), [f'{kind}{count}']) for kind in kinds for count in counts]
    schedule = list(BENCH['experiment_schedule'](plans + plans[:1], 4, random.Random(17)))
    assert len(schedule) == len(kinds) * len(counts) * 4
    for repeat in range(1, 5):
        round_plans = [plan for index, plan in schedule if index == repeat]
        assert {(plan[0], plan[1]) for plan in round_plans} == {(k, n) for k in kinds for n in counts}
        starters = []
        for offset in range(0, len(round_plans), len(kinds)):
            group = round_plans[offset:offset + len(kinds)]
            assert len({plan[1] for plan in group}) == 1  # Both platforms stay adjacent.
            assert {plan[0] for plan in group} == set(kinds)
            starters.append(group[0][0])
        for offset in range(0, len(starters) - len(kinds) + 1, len(kinds)):
            assert set(starters[offset:offset + len(kinds)]) == set(kinds)


def test_schedule_seed_is_reproducible_and_independent_of_global_random_state():
    import random

    plans = [(kind, count, Path(str(count)), []) for kind in ('vm', 'container')
             for count in (1, 2, 4, 8)]
    first = list(BENCH['experiment_schedule'](plans, 3, random.Random(42)))
    random.random()
    assert list(BENCH['experiment_schedule'](plans, 3, random.Random(42))) == first
    assert list(BENCH['experiment_schedule'](plans, 3, random.Random(43))) != first


def test_extra_container_counts_generate_only_the_additional_container_scenarios(tmp_path, monkeypatch):
    import sys

    monkeypatch.setattr(sys, 'argv', ['run.py', '--counts', '2', '2',
                                    '--container-counts', '2', '128', '256', '512', '512',
                                    '--generate-only', '--output', str(tmp_path)])
    assert BENCH['main']() == 0
    topologies = tmp_path / 'topologies'
    assert {p.name for p in (topologies / 'vm').iterdir()} == {'2'}
    assert {p.name for p in (topologies / 'container').iterdir()} == {'2', '128', '256', '512'}
    for count in (128, 256, 512):
        topology = json.loads((topologies / 'container' / str(count) / 'topology.json').read_text())
        assert len(topology['CONTAINERS']) == count
        assert topology['VMS'] == []


@pytest.mark.parametrize('arguments', [
    ['--kinds', 'vm', '--container-counts', '128'],
    ['--container-counts', '0'], ['--container-counts', '16777214'],
])
def test_invalid_extra_container_counts_fail_before_generating_files(tmp_path, monkeypatch, arguments):
    import sys

    monkeypatch.setattr(sys, 'argv', ['run.py', *arguments, '--generate-only', '--output', str(tmp_path)])
    with pytest.raises(SystemExit) as error:
        BENCH['main']()
    assert error.value.code == 2
    assert not list(tmp_path.iterdir())


def test_mixed_schedule_preserves_pair_balance_and_container_only_sizes():
    import random

    configurations = [(kind, count) for kind in ('vm', 'container') for count in (1, 2, 4, 8)]
    configurations += [('container', count) for count in (128, 256, 512)]
    plans = [(kind, count, Path(str(count)), []) for kind, count in configurations]
    schedule = list(BENCH['experiment_schedule'](plans, 4, random.Random(17)))
    for repeat in range(1, 5):
        round_plans = [plan for index, plan in schedule if index == repeat]
        assert len(round_plans) == len(configurations)
        assert {(p[0], p[1]) for p in round_plans} == set(configurations)
        firsts = []
        for index, plan in enumerate(round_plans):
            kind, count, *_ = plan
            if count >= 128:
                assert kind == 'container'
            elif index == 0 or round_plans[index - 1][1] != count:
                assert round_plans[index + 1][1] == count
                firsts.append(kind)
        for offset in range(0, len(firsts), 2):
            assert set(firsts[offset:offset + 2]) == {'vm', 'container'}


def test_extra_rounds_start_only_after_all_normal_rounds_and_preserve_their_seed():
    import random

    normal = [(kind, count, Path(str(count)), [])
              for kind in ('vm', 'container') for count in (32, 64)]
    extras = [('container', count, Path(str(count)), []) for count in (128, 256, 512)]
    schedule = list(BENCH['phased_schedule'](normal + extras, 4, random.Random(42),
                                           [128, 256, 512]))
    boundary = len(normal) * 4
    assert all(phase == 'normal' for phase, _, _ in schedule[:boundary])
    assert all(phase == 'extra' for phase, _, _ in schedule[boundary:])
    assert [(repeat, plan) for _, repeat, plan in schedule[:boundary]] == list(
        BENCH['experiment_schedule'](normal, 4, random.Random(42)))
    for repeat in range(1, 5):
        assert {plan[1] for phase, index, plan in schedule if phase == 'extra' and index == repeat} == {
            128, 256, 512}


@pytest.mark.parametrize('failure', [None, 'extra_warmup', 'extra_measurement', 'normal'])
def test_extra_execution_never_precedes_normal_csvs_and_keeps_completed_results(
        tmp_path, monkeypatch, capsys, failure):
    import csv
    from types import SimpleNamespace

    events = []
    module = BENCH['execute'].__globals__

    class IdleClient:
        def call(self, command, *_):
            assert command in ('status', 'stats', 'disk-usage')
            return {'defined': False, 'resources': []}

    def trial(_client, _path, instances, kind, count, repeat, *_args, **_kwargs):
        events.append((kind, count, repeat))
        if count == 128:
            with (tmp_path / 'startup.csv').open() as source:
                normal_rows = [r for r in csv.DictReader(source) if r['count'] == '1']
            assert len(normal_rows) == 8
            assert {r['repeat'] for r in normal_rows} == {'1', '2', '3', '4'}
            assert all(r['status'] == 'ready' for r in normal_rows)
        failed = ((failure == 'extra_warmup' and count == 128 and repeat == 0)
                  or (failure == 'extra_measurement' and count == 128 and repeat == 1)
                  or (failure == 'normal' and count == 1 and repeat == 1))
        rows = [dict(kind=kind, count=count, repeat=repeat, instance=ident,
                     status='failed' if failed else 'ready', error='injected failure' if failed else '',
                     all_ready_ms='' if failed else 100, ready_ms='' if failed else 100)
                for ident in instances]
        return rows, False

    monkeypatch.setitem(module, 'Client', lambda *_: IdleClient())
    monkeypatch.setitem(module, 'trial', trial)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_a, **_k: None)
    args = SimpleNamespace(socket='unused', rpc_timeout=600, skip_runtime_timing=True,
                           kinds=['vm', 'container'], counts=[1], container_counts=[1, 128],
                           vm_image=tmp_path, image='local:test', repeats=4, timeout=180,
                           interval=.1, seed=42, observe_seconds=10, stats_interval=1,
                           settle_seconds=2, keep_going=False)
    plans = [(kind, count, tmp_path, [f'{kind}{i}' for i in range(count)])
             for kind, count in [('vm', 1), ('container', 1), ('container', 128)]]
    with BENCH['results_files'](tmp_path) as files:
        assert BENCH['execute'](args, plans, files) == int(failure is not None)
    if failure == 'normal':
        assert all(count == 1 for _, count, _ in events)
    else:
        assert len([event for event in events if event[1] == 1]) == 10
        assert events[10] == ('container', 128, 0)
        assert 'Extra round 1/4' in capsys.readouterr().out
        if failure is None:
            assert [repeat for _, count, repeat in events if count == 128] == [0, 1, 2, 3, 4]


@pytest.mark.parametrize('kind', ['vm', 'container'])
def test_disk_rows_join_by_kind_and_instance_and_preserve_raw_sizes(kind):
    class DiskClient:
        def call(self, command):
            assert command == 'disk-usage'
            return dict(timestamp='now', resources=[
                dict(kind='other', id='vm1', disk_bytes=999, source='docker_writable_layer'),
                dict(kind=kind, id='vm2', disk_bytes=4096, file_bytes=8192, source='host_allocated_blocks'),
                dict(kind=kind, id='vm1', disk_bytes=0, file_bytes=8192, source='host_allocated_blocks')])

    rows = BENCH['disk_rows'](DiskClient(), ['vm1', 'vm2'], kind, 2, 3)
    assert [r['instance'] for r in rows] == ['vm1', 'vm2']
    assert [r['disk_bytes'] for r in rows] == [0, 4096]
    assert all(r['file_bytes'] == 8192 and r['source'] == 'host_allocated_blocks' for r in rows)
    assert all(r['status'] == 'sampled' and r['sample_timestamp'] == 'now' and r['repeat'] == 3 for r in rows)


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'error', 'negative', 'fractional', 'source'])
def test_disk_rows_do_not_replace_invalid_measurements_with_zero(mutation):
    resource = dict(kind='vm', id='vm1', disk_bytes=4096, source='host_allocated_blocks')
    resources = [resource]
    if mutation == 'missing':
        resources = []
    elif mutation == 'duplicate':
        resources *= 2
    else:
        resource.update({'error': 'stat failed'} if mutation == 'error' else
                        {'disk_bytes': -1} if mutation == 'negative' else
                        {'disk_bytes': 1.5} if mutation == 'fractional' else
                        {'source': 'docker_writable_layer'})

    class DiskClient:
        def call(self, command):
            return dict(timestamp='now', resources=resources)

    row = BENCH['disk_rows'](DiskClient(), ['vm1'], 'vm', 1, 1)[0]
    assert row['status'] == 'metrics_error'
    assert row['disk_bytes'] == '' and row['error']


def test_disk_collection_failure_preserves_readiness_and_cleanup(tmp_path):
    client, saved = Client(fail='disk-usage'), []
    rows, stop = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0, save_disk=saved.extend)
    assert not stop and rows[0]['status'] == 'ready'
    assert len(saved) == 1 and saved[0]['status'] == 'collection_failed'
    assert saved[0]['disk_bytes'] == ''
    assert client.calls[-2:] == ['topodown', 'topodestroy']


@pytest.mark.parametrize('image_bytes', [8192, None, -1, True, 1.5])
def test_disk_rows_keep_image_measurement_separate_from_private_size(image_bytes):
    class DiskClient:
        def call(self, *_):
            return dict(timestamp='now', resources=[dict(
                kind='container', id='c1', disk_bytes=1024, source='docker_writable_layer',
                image_id='sha256:actual', image_bytes=image_bytes, image_source='docker_image_size')])

    row = BENCH['disk_rows'](DiskClient(), ['c1'], 'container', 1, 1)[0]
    assert row['status'] == 'sampled' and row['disk_bytes'] == 1024
    if type(image_bytes) is int and image_bytes >= 0:
        assert row['image_bytes'] == image_bytes
        assert row['image_id'] == 'sha256:actual'
        assert not row['image_error']
    else:
        assert row['image_bytes'] == '' and row['image_error']


def test_interrupt_during_disk_collection_still_cleans_and_retains_startup_times(tmp_path):
    class InterruptedDiskClient(Client):
        def call(self, *args):
            if args[0] == 'disk-usage':
                raise KeyboardInterrupt
            return super().call(*args)

    client, saved = InterruptedDiskClient(), []
    rows, stop = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0, save_disk=saved.extend)
    assert stop and rows[0]['status'] == 'interrupted'
    assert rows[0]['ready_ms'] != ''
    assert len(saved) == 1 and saved[0]['status'] == 'interrupted' and saved[0]['disk_bytes'] == ''
    assert client.calls[-2:] == ['topodown', 'topodestroy']


@pytest.mark.parametrize('failure', ['private', 'image'])
def test_disk_failure_is_reported_without_polluting_other_csvs(tmp_path, monkeypatch, failure):
    import csv
    from types import SimpleNamespace

    class DiskFailureClient(Client):
        disk_calls = 0

        def call(self, *args):
            if args[0] == 'status':
                return {'defined': False}
            if args[0] == 'stats':
                return {'resources': []}
            if args[0] == 'disk-usage':
                self.disk_calls += 1
                if self.disk_calls > 1:  # Preflight succeeds; warmup and measurement fail collection.
                    if failure == 'private':
                        raise RuntimeError('disk collection failed')
                    response = super().call(*args)
                    for row in response['resources']:
                        row.update(image_error='image unavailable')
                    return response
            return super().call(*args)

    client = DiskFailureClient()
    module = BENCH['execute'].__globals__
    monkeypatch.setitem(module, 'Client', lambda *_args: client)
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs: None)
    args = SimpleNamespace(socket='unused', rpc_timeout=600, skip_runtime_timing=True,
                           kinds=['container'], image='local:test', repeats=1, timeout=1, seed=42,
                           interval=0, observe_seconds=0, stats_interval=1, settle_seconds=0, keep_going=True)
    with BENCH['results_files'](tmp_path) as files:
        assert BENCH['execute'](args, [('container', 1, tmp_path, ['c1'])], files) == 1
    with (tmp_path / 'startup.csv').open() as source:
        rows = list(csv.DictReader(source))
        assert len(rows) == 1 and rows[0]['status'] == 'ready'
    with (tmp_path / 'disk_usage.csv').open() as source:
        rows = list(csv.DictReader(source))
        assert len(rows) == 1
        if failure == 'private':
            assert rows[0]['status'] == 'collection_failed' and rows[0]['disk_bytes'] == ''
        else:
            assert rows[0]['status'] == 'sampled' and rows[0]['disk_bytes'] == '1024'
            assert rows[0]['image_error'] == 'image unavailable'
    assert client.disk_calls == 3
    assert client.calls.count('topodestroy') == 2
