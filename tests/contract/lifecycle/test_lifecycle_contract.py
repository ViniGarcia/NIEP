import pytest

from niep.application.service import TopologyService
from niep.domain.result import ResultCode
from niep.application.lifecycle import TopologyState
from tests.check_teardown import build_executor
import niep.application.service as service_module


class FakeExecutor:
    """Small public-boundary double with typed lifecycle state."""

    def __init__(self):
        self.lifecycle_state = TopologyState.DEFINED
        self.STATUS = None
        self.CLEANUP_REQUIRED = True
        self.CLEANUP_ERRORS = []
        self.DETAIL = ""
        self.calls = []

    def topologyUp(self):
        self.calls.append("up")
        self.lifecycle_state = TopologyState.UP
        self.STATUS = 0
        self.CLEANUP_REQUIRED = True
        return 0

    def topologyDown(self):
        self.calls.append("down")
        self.lifecycle_state = TopologyState.DOWN
        self.STATUS = None
        self.CLEANUP_REQUIRED = False
        return 0

    def rollbackFailedStart(self):
        self.calls.append("rollback")
        self.CLEANUP_REQUIRED = False
        return []


class DefinitionParser:
    STATUS = 0
    SPEC = object()


class DefinitionFactory:
    def materialize(self, _spec):
        return object()


def definition_service(*, empty_executor=True):
    def make_executor(_configuration):
        executor = FakeExecutor()
        if empty_executor:
            executor.CLEANUP_REQUIRED = False
        return executor

    return TopologyService(
        runtime_factory=DefinitionFactory(),
        executor_factory=make_executor,
        parser_factory=lambda _path: DefinitionParser(),
    )


def test_public_commands_use_typed_state_and_preserve_result_codes():
    executor = FakeExecutor()
    service = TopologyService()
    service.executor = executor

    started = service.up()
    assert started.ok and started.code is ResultCode.TOPOLOGY_UP
    assert service.state is TopologyState.UP
    repeated = service.up()
    assert not repeated.ok and repeated.code is ResultCode.ALREADY_EXECUTED

    stopped = service.down()
    assert stopped.ok and stopped.code is ResultCode.TOPOLOGY_DOWN
    assert service.state is TopologyState.DOWN
    cleaned = service.clean()
    assert cleaned.ok and cleaned.code is ResultCode.TOPOLOGY_CLEAN
    assert service.state is TopologyState.UNDEFINED


def test_cleanup_is_idempotent_at_executor_boundary():
    executor = FakeExecutor()
    service = TopologyService()
    service.executor = executor
    assert service.up().ok
    assert service.down().ok
    # A repeated down is a successful no-op and does not call runtime again.
    assert service.down().ok
    assert executor.calls == ["up", "down"]


def test_define_down_aligns_executor_and_service_and_allows_restart():
    executor = FakeExecutor()
    executor.CLEANUP_REQUIRED = False
    service = TopologyService()
    service.executor = executor

    stopped = service.down()
    assert stopped.ok
    assert service.state is TopologyState.DOWN
    assert executor.lifecycle_state is TopologyState.DOWN
    assert executor.calls == ["down"]

    restarted = service.up()
    assert restarted.ok
    assert service.state is TopologyState.UP
    assert executor.lifecycle_state is TopologyState.UP
    assert executor.calls == ["down", "up"]


def test_define_up_down_define_discards_only_reconciled_executor():
    service = definition_service(empty_executor=False)
    first = service.define("first.json")
    old_executor = first.data
    assert first.ok
    assert service.up().ok
    assert service.down().ok

    second = service.define("second.json")

    assert second.ok and second.data is not old_executor
    assert service.state is TopologyState.DEFINED


def test_define_twice_is_allowed_when_defined_executor_has_no_resources():
    service = definition_service()
    first = service.define("first.json")
    old_executor = first.data

    second = service.define("second.json")

    assert first.ok and second.ok
    assert second.data is not old_executor
    assert service.state is TopologyState.DEFINED


@pytest.mark.parametrize(
    "state",
    (
        TopologyState.UP,
        TopologyState.STARTING,
        TopologyState.STOPPING,
        TopologyState.FAILED,
        TopologyState.CLEANUP_PENDING,
    ),
)
def test_define_rejects_active_or_pending_executor_states(state):
    service = definition_service(empty_executor=False)
    result = service.define("first.json")
    executor = result.data
    executor.lifecycle_state = state
    service._lifecycle.force(state)

    rejected = service.define("second.json")

    assert not rejected.ok
    assert rejected.code is ResultCode.ALREADY_EXECUTED
    assert service.executor is executor


def test_cleanup_pending_requires_cleanup_before_new_up():
    executor = FakeExecutor()
    executor.lifecycle_state = TopologyState.CLEANUP_PENDING
    service = TopologyService()
    service.executor = executor

    result = service.up()

    assert not result.ok
    assert result.code is ResultCode.TOPOLOGY_UP_FAILED
    assert executor.calls == []


def test_persistent_destroy_failure_is_cleanup_pending_and_retryable(monkeypatch):
    executor, _ = build_executor()
    service = TopologyService()
    service.executor = executor
    monkeypatch.setattr(service_module, "exists", lambda _path: True)
    calls = {"count": 0}

    def remove(_path):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("busy")

    monkeypatch.setattr(service_module, "rmtree", remove)
    failed = service.destroy()
    assert not failed.ok
    assert service.state is TopologyState.CLEANUP_PENDING
    assert service.executor is executor

    retried = service.destroy()
    assert retried.ok and retried.code is ResultCode.TOPOLOGY_DESTROYED
    assert service.state is TopologyState.DESTROYED
