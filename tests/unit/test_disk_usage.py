from types import SimpleNamespace
import json

from typer.testing import CliRunner

from niep.application.command import CommandDispatcher
from niep.application.disk_usage import DiskUsageService
from niep.interfaces import niepctl
from niep.runtime.disk_usage import container_disk_usage, vm_disk_usage


def test_vm_disk_usage_counts_allocated_blocks_for_sparse_files(tmp_path):
    path = tmp_path / 'disk.qcow2'
    with path.open('wb') as handle:
        handle.truncate(1024 * 1024)
        handle.write(b'data')
    vm = SimpleNamespace(ID='v1', DISK='alpine-http', VM_EXIST=True,
                         IMAGE_STORE=SimpleNamespace(instance_disk_path=lambda *_: path))
    data = vm_disk_usage(vm)
    assert data['disk_bytes'] == path.stat().st_blocks * 512
    assert data['file_bytes'] == 1024 * 1024
    assert data['disk_bytes'] < data['file_bytes']


def test_container_uses_exact_id_filter_and_only_private_writable_layer():
    def containers(**kwargs):
        assert kwargs == dict(all=True, size=True, filters={'id': ['container-id']})
        return [{'Id': 'container-id', 'SizeRw': 1234, 'SizeRootFs': 999999}]

    resource = SimpleNamespace(CONTAINER=SimpleNamespace(
        id='container-id', client=SimpleNamespace(api=SimpleNamespace(containers=containers))))
    assert container_disk_usage(resource)['disk_bytes'] == 1234
    assert container_disk_usage(SimpleNamespace(CONTAINER=None))['disk_bytes'] == 0


def test_disk_totals_preserve_other_measurements_after_runtime_failure():
    class Session:
        def resource_ids(self, group):
            return ['v1'] if group == 'vms' else ['c1']

        def get_resource(self, *_):
            return None

    def unavailable(_):
        raise RuntimeError('Docker unavailable')

    service = DiskUsageService(Session(), vm_reader=lambda _: {'disk_bytes': 200},
                               container_reader=unavailable)
    data = service.snapshot().data
    assert data['resources'][1]['error'] == 'Docker unavailable'
    assert data['resources'][1]['disk_bytes'] is None
    assert data['totals']['workloads'] == dict(disk_bytes=200, resources=2,
                                              measured_resources=1, partial=True)
    assert not service.snapshot(('unexpected',)).ok


def test_idle_disk_usage_protocol():
    dispatcher = CommandDispatcher()
    response = dispatcher.dispatch_request({'command': 'disk-usage'}).to_dict()
    assert response['ok']
    assert response['data']['resources'] == []
    assert response['data']['totals']['workloads']['disk_bytes'] == 0
    assert not dispatcher.dispatch('disk-usage', ['extra']).ok
    json.dumps(response)


def test_disk_usage_cli_table_and_json(monkeypatch):
    response = {'ok': True, 'data': {'resources': [
        {'kind': 'vm', 'id': 'v1', 'disk_bytes': 1048576, 'source': 'host_allocated_blocks'}],
        'totals': {'workloads': {'disk_bytes': 1048576, 'measured_resources': 1, 'resources': 1}}}}
    monkeypatch.setattr(niepctl, 'request', lambda *_: response)
    runner = CliRunner()
    table = runner.invoke(niepctl.app, ['disk-usage'])
    assert table.exit_code == 0
    assert 'v1' in table.stdout
    assert '1.00 MiB' in table.stdout
    raw = runner.invoke(niepctl.app, ['--json', 'disk-usage'])
    assert raw.exit_code == 0
    assert json.loads(raw.stdout) == response
