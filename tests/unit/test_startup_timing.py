from types import SimpleNamespace
import threading
import time

from niep.application.startup_timing import StartupTimingService
from niep.domain.result import ResultCode, ServiceResult
from niep.runtime.libvirt import LibvirtRuntime
from niep.runtime.docker import DockerRuntime


def session():
    return SimpleNamespace(is_up=lambda: False)


def test_actual_libvirt_start_is_timed_and_probe_runs_before_api_returns():
    entered, observed = threading.Event(), threading.Event()

    def factory(_resource):
        def probe(_timeout):
            if entered.is_set():
                observed.set()
                return time.perf_counter_ns()
            return None
        return probe

    service = StartupTimingService(session(), vm_factory=factory)
    assert service.handle(('arm', '1', '.001')).ok

    def create():
        entered.set()
        assert observed.wait(1)
        return 0

    domain = SimpleNamespace(name=lambda: 'vm1', UUIDString=lambda: 'uuid', create=create)

    def up(_args):
        LibvirtRuntime().start(domain)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP)

    assert service.up((), up).ok
    data = service.handle(('snapshot',)).data
    assert len(data['resources']) == 1
    record = data['resources'][0]
    assert record['id'] == 'vm1'
    assert record['status'] == 'ready'
    assert record['runtime_ready_ms'] <= record['start_call_ms']
    # A single arm must not instrument a later independent up.
    service.up((), up)
    assert len(service.handle(('snapshot',)).data['resources']) == 1


def test_docker_counter_stops_before_reload_and_status_validation():
    service = StartupTimingService(session(), container_factory=lambda _: lambda timeout: time.perf_counter_ns())
    service.handle(('arm', '1', '.001'))
    observed = []

    def reload():
        observed.append(service.handle(('snapshot',)).data['resources'][0]['start_call_ms'])

    handle = SimpleNamespace(name='c1', id='id1', status='running', start=lambda: None, reload=reload)

    def up(_args):
        DockerRuntime().start(handle)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP)

    service.up((), up)
    record = service.handle(('snapshot',)).data['resources'][0]
    assert observed[0] is not None
    assert record['start_call_ms'] == observed[0]
    service.tickets[0].thread.join(timeout=1)
    assert service.handle(('snapshot',)).data['resources'][0]['status'] == 'ready'


def test_failed_probe_does_not_prevent_platform_start():
    def broken(_):
        raise RuntimeError('No management network')

    created = []
    service = StartupTimingService(session(), vm_factory=broken)
    service.handle(('arm', '1', '.01'))
    domain = SimpleNamespace(name=lambda: 'vm', UUIDString=lambda: 'uuid', create=lambda: created.append(True))

    def up(_args):
        LibvirtRuntime().start(domain)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP)

    assert service.up((), up).ok
    assert created
    assert service.handle(('snapshot',)).data['resources'][0]['status'] == 'probe_failed'


def test_stop_cancels_pending_probe_and_arguments_are_validated():
    service = StartupTimingService(session(), vm_factory=lambda _: lambda timeout: None)
    assert not service.handle(('arm', 'nan', '.1')).ok
    assert not service.handle(('arm', '2', '0')).ok
    assert not service.handle(('unexpected',)).ok
    service.handle(('arm', '1', '.01'))
    resource = SimpleNamespace(name=lambda: 'vm', UUIDString=lambda: 'uuid')
    ticket = service.prepare('vm', resource)
    ticket.begin()
    service.stop((), lambda _: ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DOWN))
    ticket.thread.join(timeout=1)
    assert service.handle(('snapshot',)).data['resources'][0]['status'] == 'cancelled'


def test_runtime_start_failure_is_recorded_and_raised():
    import pytest
    from niep.runtime.errors import RuntimeFailure

    service = StartupTimingService(session(), vm_factory=lambda _: lambda timeout: None)
    service.handle(('arm', '1', '.01'))

    def create():
        raise RuntimeError('Hypervisor rejected start')

    domain = SimpleNamespace(name=lambda: 'vm', UUIDString=lambda: 'uuid', create=create)
    with pytest.raises(RuntimeFailure):
        service.up((), lambda _: LibvirtRuntime().start(domain))
    record = service.handle(('snapshot',)).data['resources'][0]
    assert record['status'] == 'start_failed'
    assert 'Hypervisor rejected start' in record['error']
    assert record['start_call_ms'] is not None
