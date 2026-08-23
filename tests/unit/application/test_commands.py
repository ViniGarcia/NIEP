import json

import pytest

from niep.application.command import CommandDispatcher, _public_result
from niep.application.commands import CommandResponse
from niep.application.handlers import MininetCommandHandler, TopologyCommandHandler
from niep.application.session import TopologySession
from niep.domain.result import ResultCode, ServiceResult


pytestmark = pytest.mark.unit


def test_router_has_aggregate_registry_without_runtime_data():
    dispatcher = CommandDispatcher()
    assert set(dispatcher.router.routes) == {
        "container",
        "define",
        "mininet",
        "sfc",
        "status",
        "topoclean",
        "topodestroy",
        "topodown",
        "topoup",
        "vm",
        "vnf",
    }
    result = dispatcher.dispatch("status")
    assert result.data == {
        "defined": False,
        "up": False,
        "vms": [],
        "containers": [],
        "vnfs": [],
        "sfcs": [],
    }
    json.dumps(result.to_dict())


def test_public_topology_result_does_not_expose_executor():
    private = object()
    result = ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP, data=private)
    public = _public_result(result)
    assert public.data is None
    json.dumps(public.to_dict())


def test_unknown_public_data_fails_closed_without_stringifying_secrets():
    class Secret:
        def __str__(self):
            return "password=do-not-leak"

    public = _public_result(ServiceResult(ok=True, code=ResultCode.STATUS, data=Secret()))
    assert public.ok is False
    assert public.code is ResultCode.COMMAND_ERROR
    assert "password" not in public.message
    assert "password" not in str(public.to_dict())


def test_command_response_rejects_runtime_objects():
    with pytest.raises(Exception):
        CommandResponse(
            request_id="bad-data",
            ok=True,
            code="status",
            data=object(),
        )


def test_session_has_no_public_executor_attribute():
    session = TopologySession()
    assert not hasattr(session, "executor")


def test_handlers_use_the_session_port_without_executor_fields():
    class SessionPort:
        def status(self):
            return {"defined": False, "up": False, "vms": [], "containers": [], "vnfs": [], "sfcs": []}

        def is_up(self):
            return False

        def __getattr__(self, name):
            if name == "executor":
                raise AssertionError("handler reached through executor")
            raise AttributeError(name)

    session = SessionPort()
    assert TopologyCommandHandler(session).status(()).data["defined"] is False
    assert MininetCommandHandler(session).handle(("pingall",)).code is ResultCode.TOPOLOGY_NOT_UP


def test_legacy_dispatch_preserves_invalid_args_code():
    result = CommandDispatcher().dispatch("vnf", ["management"])
    assert result.code is ResultCode.INVALID_COMMAND_ARGS
    assert result.message == "WRONG ARGUMENTS AMOUNT - 2 EXPECTED"
