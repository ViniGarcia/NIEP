"""Benchmark integrity: distinct identities, HTTP evidence, and cleanup failures."""
import json
from pathlib import Path
import runpy

import pytest


BENCH = runpy.run_path(str(Path(__file__).resolve().parents[3] / 'benchmarks/startup/run.py'))


@pytest.mark.parametrize('kind', ['vm', 'container'])
@pytest.mark.parametrize('count', [1, 2, 4, 8, 16])
def test_generated_topologies_have_unique_interfaces(tmp_path, kind, count):
    path, instances = BENCH['generate'](tmp_path, kind, count, 'local:test')
    topology = json.loads(path.read_text())
    assert len(topology['CONNECTIONS']) == count
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


def test_interrupt_saves_partial_observations_and_cleans(tmp_path):
    class InterruptedClient(Client):
        def call(self, *args):
            if args[0] == 'mininet':
                raise KeyboardInterrupt
            return super().call(*args)

    client = InterruptedClient()
    rows, stop = BENCH['trial'](client, tmp_path, ['vm1'], 'vm', 1, 1, 1, 0)
    assert stop
    assert rows[0]['status'] == 'interrupted'
    assert client.calls[-2:] == ['topodown', 'topodestroy']


@pytest.mark.parametrize('count, passes', [(1, True), (16, False)])
def test_image_preflight_detects_original_single_mac_base(tmp_path, monkeypatch, count, passes):
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
            return '52:54:02:20:10:01 10.20.0.2/24\n'
        raise AssertionError(args)

    monkeypatch.setitem(helper['process'].__globals__, 'command', fake_command)
    if passes:
        helper['process'](source, count=count)
    else:
        with pytest.raises(RuntimeError, match='lacks 15 required MAC mappings'):
            helper['process'](source, count=count)
    assert source.read_bytes() == b'original'


def test_repeated_runs_append_one_csv_and_remove_temporary_topologies(tmp_path, monkeypatch):
    import csv
    import sys
    from types import SimpleNamespace

    class IdleClient(Client):
        def call(self, *args):
            if args[0] == 'status':
                return {'defined': False}
            return super().call(*args)

    module = BENCH['main'].__globals__
    monkeypatch.setitem(module, 'Client', lambda *_args: IdleClient())
    monkeypatch.setattr(module['subprocess'], 'run', lambda *_args, **_kwargs:
                        SimpleNamespace(stdout='[{"Id":"sha256:test"}]'))
    monkeypatch.setattr(sys, 'argv', ['run.py', '--kinds', 'container', '--counts', '1',
                                    '--repeats', '1', '--output', str(tmp_path)])
    assert BENCH['main']() == 0
    first = (tmp_path / 'results.csv').read_bytes()
    assert BENCH['main']() == 0
    assert (tmp_path / 'results.csv').read_bytes().startswith(first)
    with (tmp_path / 'results.csv').open(newline='') as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 2
    assert rows[0]['run_id'] != rows[1]['run_id']
    assert all(row['image_id'] == 'sha256:test' for row in rows)
    assert all(json.loads(row['config_json'])['counts'] == [1] for row in rows)
    assert list(tmp_path.iterdir()) == [tmp_path / 'results.csv']


def test_csv_with_incompatible_header_is_preserved(tmp_path):
    path = tmp_path / 'results.csv'
    original = 'old,header\n1,2\n'
    path.write_text(original)
    with pytest.raises(RuntimeError, match='Incompatible CSV header'):
        with BENCH['results_file'](path):
            pytest.fail('incompatible CSV must not be opened for writing')
    assert path.read_text() == original


def test_csv_rejects_concurrent_writer(tmp_path):
    path = tmp_path / 'results.csv'
    with BENCH['results_file'](path):
        with pytest.raises(RuntimeError, match='Another benchmark'):
            with BENCH['results_file'](path):
                pytest.fail('second writer must not acquire the file')
