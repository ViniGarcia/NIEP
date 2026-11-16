from types import SimpleNamespace
import json
import os

import pytest

from typer.testing import CliRunner

from niep.application.command import CommandDispatcher
from niep.application.disk_usage import DiskUsageService
from niep.interfaces import niepctl
from niep.runtime.disk_usage import (
    allocated_tree_bytes, container_disk_usage, container_image_usage, container_upper_dir,
    vm_disk_usage,
)


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
        id='container-id', client=SimpleNamespace(api=SimpleNamespace(
            base_url='http://remote:2375', containers=containers))))
    assert container_disk_usage(resource)['disk_bytes'] == 1234
    assert container_disk_usage(SimpleNamespace(CONTAINER=None))['disk_bytes'] == 0


def test_allocated_tree_counts_sparse_files_directories_and_hardlinks_once(tmp_path):
    upper = tmp_path / 'upper'
    upper.mkdir()
    nested = upper / 'nested'
    nested.mkdir()
    sparse = nested / 'sparse'
    with sparse.open('wb') as handle:
        handle.truncate(16 * 1024 * 1024)
        handle.write(b'data')
    os.link(sparse, upper / 'hardlink')
    outside = tmp_path / 'outside'
    outside.write_bytes(b'outside' * 4096)
    symlink = upper / 'symlink'
    symlink.symlink_to(outside)
    directory_link = nested / 'loop'
    directory_link.symlink_to(upper, target_is_directory=True)
    expected = sum(p.lstat().st_blocks * 512
                   for p in (upper, nested, sparse, symlink, directory_link))
    assert allocated_tree_bytes(upper) == expected
    assert expected < sparse.stat().st_size


def local_container(upper, size=1234):
    return SimpleNamespace(CONTAINER=SimpleNamespace(
        id='container-id', client=SimpleNamespace(api=SimpleNamespace(
            base_url='http+docker://localhost',
            inspect_container=lambda _: {'GraphDriver': {'Data': {'UpperDir': upper}}},
            containers=lambda **_: [{'Id': 'container-id', 'SizeRw': size}]))))


def test_local_container_prefers_allocated_blocks_over_logical_size(tmp_path):
    resource = local_container(str(tmp_path), size=99999999)
    assert container_disk_usage(resource) == {
        'disk_bytes': tmp_path.stat().st_blocks * 512, 'source': 'host_allocated_blocks'}


@pytest.mark.parametrize('upper', [None, '/nonexistent/niep-test-upperdir'])
def test_container_falls_back_when_writable_directory_is_unavailable(upper):
    assert container_disk_usage(local_container(upper)) == {
        'disk_bytes': 1234, 'source': 'docker_writable_layer'}


def test_container_never_returns_partial_directory_walk(monkeypatch, tmp_path):
    def denied(_):
        raise PermissionError('cannot scan')

    monkeypatch.setattr('niep.runtime.disk_usage.os.scandir', denied)
    assert container_disk_usage(local_container(str(tmp_path))) == {
        'disk_bytes': 1234, 'source': 'docker_writable_layer'}


def test_containerd_null_graph_driver_uses_root_overlay_mount(monkeypatch, tmp_path):
    upper = tmp_path / 'upper dir'
    upper.mkdir()
    escaped = str(upper).replace(' ', r'\040')

    def mountinfo(path):
        assert str(path) == '/proc/42/mountinfo'
        return ('20 1 0:3 / /data rw - overlay overlay rw,upperdir=/wrong\n'
                '21 1 0:4 / / rw shared:9 - overlay overlay '
                f'rw,lowerdir=/shared/image,upperdir={escaped},workdir=/work\n')

    monkeypatch.setattr('niep.runtime.disk_usage.Path.read_text', mountinfo)
    resource = local_container(None)
    resource.CONTAINER.client.api.inspect_container = lambda _: {
        'GraphDriver': None, 'State': {'Pid': 42}}
    assert container_disk_usage(resource) == {
        'disk_bytes': upper.stat().st_blocks * 512, 'source': 'host_allocated_blocks'}


@pytest.mark.parametrize('info', [
    {'GraphDriver': None}, {'State': {'Pid': 0}}, {'State': {'Pid': -1}},
    {'State': {'Pid': '42'}},
])
def test_uncreated_or_stopped_containerd_has_no_host_layer_path(info):
    assert container_upper_dir(info) is None


@pytest.mark.parametrize('size', [None, -1, True, 1.5, '1234'])
def test_container_rejects_invalid_docker_sizes(size):
    with pytest.raises(RuntimeError, match='did not report'):
        container_disk_usage(local_container(None, size=size))


def test_image_size_uses_actual_immutable_image_and_caches_once_per_snapshot():
    inspected = []

    def inspect_image(image_id):
        inspected.append(image_id)
        return {'Size': 987654}

    api = SimpleNamespace(base_url='http+docker://localhost',
                          inspect_container=lambda _: {'Image': 'sha256:actual'},
                          inspect_image=inspect_image)
    cache = {}
    for ident in ('c1', 'c2'):
        container = SimpleNamespace(CONTAINER=SimpleNamespace(
            id=ident, client=SimpleNamespace(api=api)))
        assert container_image_usage(container, cache) == dict(
            image_id='sha256:actual', image_bytes=987654, image_source='docker_image_size')
    assert inspected == ['sha256:actual']


@pytest.mark.parametrize('size', [None, -1, True, 1.5])
def test_invalid_image_size_is_not_cached(size):
    resource = local_container(None)
    resource.CONTAINER.client.api.inspect_container = lambda _: {'Image': 'sha256:actual'}
    resource.CONTAINER.client.api.inspect_image = lambda _: {'Size': size}
    cache = {}
    with pytest.raises(RuntimeError, match='valid image size'):
        container_image_usage(resource, cache)
    assert cache == {}


def test_image_failure_preserves_private_disk_and_has_its_own_error():
    class Session:
        def resource_ids(self, group):
            return ['c1'] if group == 'containers' else []

        def get_resource(self, *_):
            return None

    def unavailable(_, cache):
        raise RuntimeError('Image unavailable')

    service = DiskUsageService(Session(), container_reader=lambda _: {'disk_bytes': 1234},
                               image_reader=unavailable)
    data = service.snapshot().data
    assert data['resources'][0]['disk_bytes'] == 1234
    assert data['resources'][0]['error'] is None
    assert data['resources'][0]['image_bytes'] is None
    assert data['resources'][0]['image_error'] == 'Image unavailable'
    assert not data['totals']['containers']['partial']


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
