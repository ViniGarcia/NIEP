from types import SimpleNamespace
import json

from typer.testing import CliRunner

from niep.application.metrics import MetricsService
from niep.application.command import CommandDispatcher
from niep.interfaces import niepctl
from niep.runtime.metrics import vm_counters, container_counters


class Session:
    def resource_ids(self, group):
        return ['v1'] if group == 'vms' else ['c1']

    def get_resource(self, kind, ident):
        return ident


def test_rates_totals_restarts_and_errors():
    now = [0]
    cpu = [0]
    identity = ['first']
    bad = [False]

    def read(_resource=None):
        if bad[0]:
            raise RuntimeError('runtime unavailable')
        return dict(state='running', identity=identity[0], cpu_time_ns=cpu[0], memory_bytes=1024)

    service = MetricsService(Session(), vm_reader=read, container_reader=read,
                             daemon_reader=read, clock=lambda: now[0])
    first = service.snapshot().data
    assert first['resources'][0]['cpu_percent'] is None
    assert first['totals']['workloads']['partial']
    now[0], cpu[0] = 5, 10_000_000_000
    second = service.snapshot().data
    assert second['resources'][0]['cpu_percent'] == 200
    assert second['totals']['workloads']['cpu_percent'] == 400
    assert second['totals']['with_daemon']['memory_bytes'] == 3072
    assert not second['totals']['workloads']['partial']
    identity[0] = 'restarted'
    now[0] += 5
    assert service.snapshot().data['resources'][0]['cpu_percent'] is None
    bad[0] = True
    failed = service.snapshot().data
    assert failed['resources'][0]['error'] == 'runtime unavailable'
    assert failed['totals']['workloads']['partial']
    assert failed['totals']['workloads']['memory_samples'] == 0


def test_stopped_resource_and_deleted_cache():
    session = Session()
    service = MetricsService(session, vm_reader=lambda _: dict(
        state='stopped', identity=None, cpu_time_ns=0, memory_bytes=0),
        container_reader=lambda _: dict(state='running', identity='c1', cpu_time_ns=12,
                                       memory_bytes=50),
        daemon_reader=lambda: dict(state='running', identity='daemon', cpu_time_ns=0, memory_bytes=1))
    data = service.snapshot().data
    assert data['resources'][0]['cpu_percent'] == 0
    session.resource_ids = lambda _: []
    assert service.snapshot().data['totals']['workloads']['resources'] == 0
    assert set(service.previous) == {('daemon', 'niepd')}
    assert not service.snapshot(('unexpected',)).ok


def test_vm_rss_and_cpu_counters():
    domain = SimpleNamespace(isActive=lambda: True, info=lambda: (1, 262144, 1000, 1, 123),
                             memoryStats=lambda: {'rss': 32000}, UUIDString=lambda: 'uuid',
                             ID=lambda: 7)
    data = vm_counters(SimpleNamespace(VIRT_VM=domain))
    assert data['memory_bytes'] == 32000 * 1024
    assert data['cpu_time_ns'] == 123
    assert data['identity'] == 'uuid:7'


def test_docker_stats_are_nonstreaming_and_one_shot():
    def stats(**kwargs):
        assert kwargs == dict(stream=False, one_shot=True)
        return {'cpu_stats': {'cpu_usage': {'total_usage': 200}},
                'memory_stats': {'usage': 2048, 'limit': 4096}}

    container = SimpleNamespace(reload=lambda: None, status='running', id='abc',
                                attrs={'State': {'StartedAt': 'today'}}, stats=stats)
    data = container_counters(SimpleNamespace(CONTAINER=container))
    assert data['memory_bytes'] == 2048
    assert data['cpu_time_ns'] == 200


def test_stats_protocol_with_idle_topology():
    dispatcher = CommandDispatcher()
    response = dispatcher.dispatch_request({'command': 'stats'}).to_dict()
    assert response['ok']
    assert response['data']['resources'] == []
    assert response['data']['daemon']['memory_bytes'] > 0
    json.dumps(response)
    assert not dispatcher.dispatch('stats', ['invalid']).ok


def test_cli_snapshot_and_default_poll_interval(monkeypatch):
    snapshot = dict(timestamp='now', resources=[], daemon=dict(
        kind='daemon', id='niepd', cpu_percent=None, memory_bytes=1024, state='running'), totals={})
    monkeypatch.setattr(niepctl, 'request', lambda *_: {'ok': True, 'data': snapshot})
    runner = CliRunner()
    result = runner.invoke(niepctl.app, ['stats-snapshot'])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == snapshot
    waits = []
    monkeypatch.setattr(niepctl.time, 'monotonic', lambda: 0)

    def sleep(interval):
        waits.append(interval)
        raise KeyboardInterrupt

    monkeypatch.setattr(niepctl.time, 'sleep', sleep)
    result = runner.invoke(niepctl.app, ['stats'])
    assert result.exit_code == 0
    assert 'niepd' in result.stdout
    assert waits == [5]
    assert runner.invoke(niepctl.app, ['stats', '--interval', '0']).exit_code != 0
