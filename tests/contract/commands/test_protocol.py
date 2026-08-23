import json
import ast
from pathlib import Path

import pytest

from niep.application.commands import (
    COMMAND_PROTOCOL,
    COMMAND_VERSION,
    CommandProtocolError,
    CommandRequest,
)
from niep.application.command import CommandDispatcher, _public_result
from niep.domain.result import ResultCode, ServiceResult
from niep.interfaces.socket_server import NIEPSocketServer


pytestmark = pytest.mark.contract


def test_request_is_versioned_immutable_and_json_safe():
    request = CommandRequest.from_dict(
        {
            "protocol": COMMAND_PROTOCOL,
            "version": COMMAND_VERSION,
            "request_id": "contract-1",
            "command": "status",
            "args": [],
            "options": {"nested": ["safe"]},
        }
    )
    assert request.to_dict()["protocol"] == COMMAND_PROTOCOL
    assert request.to_dict()["version"] == COMMAND_VERSION
    assert json.loads(request.to_json())["request_id"] == "contract-1"
    with pytest.raises(AttributeError):
        request.command = "define"


@pytest.mark.parametrize("version", [True, 1.0, "1", 2])
def test_request_rejects_non_v1_versions(version):
    with pytest.raises(CommandProtocolError):
        CommandRequest.from_dict({"command": "status", "version": version})


def test_request_rejects_unknown_fields_and_non_string_args():
    with pytest.raises(CommandProtocolError):
        CommandRequest.from_dict({"command": "status", "unknown": True})
    with pytest.raises(CommandProtocolError):
        CommandRequest.from_dict({"command": "status", "args": [1]})


def test_dispatcher_and_socket_share_the_same_public_response_shape():
    dispatcher = CommandDispatcher()
    response = dispatcher.dispatch_request(CommandRequest("status", request_id="same-1"))
    socket_response = NIEPSocketServer(dispatcher=dispatcher).handle_request(
        {"command": "status", "request_id": "same-1"}
    )
    assert response.to_dict() == socket_response
    json.dumps(socket_response)
    assert socket_response["code"] == "status"
    assert socket_response["data"]["defined"] is False


def test_defined_aggregate_lists_remain_public_but_internal_objects_do_not():
    class FakeTopology:
        def is_defined(self):
            return True

        def is_up(self):
            return True

        def vm_ids(self):
            return ["vm-1"]

        def container_ids(self):
            return ["container-1"]

        def vnf_ids(self):
            return ["vnf-1"]

        def sfc_ids(self):
            return ["sfc-1"]

        def get_vm(self, _resource_id):
            return None

        def get_container(self, _resource_id):
            return None

        def get_vnf(self, _resource_id):
            return None

        def get_sfc(self, _resource_id):
            return None

    dispatcher = CommandDispatcher(FakeTopology())
    for aggregate, resource_id in (
        ("vm", "vm-1"),
        ("container", "container-1"),
        ("vnf", "vnf-1"),
        ("sfc", "sfc-1"),
    ):
        direct = dispatcher.dispatch(aggregate, ["list"])
        assert direct.ok is True
        assert direct.data == [resource_id]
        request = {"command": aggregate, "args": ["list"], "request_id": aggregate}
        response = dispatcher.dispatch_request(request)
        assert response.to_dict()["data"] == [resource_id]
        socket_response = NIEPSocketServer(dispatcher=dispatcher).handle_request(request)
        assert socket_response["data"] == [resource_id]

    internal = ServiceResult(ok=True, code=ResultCode.DEFINED, data=object())
    assert CommandDispatcher().dispatch_request(
        CommandRequest("status", request_id="defined-safe")
    ).data["defined"] is False
    assert _public_result(internal).data is None


def test_unknown_command_is_structured_and_has_process_exit_code():
    response = CommandDispatcher().dispatch_request(CommandRequest("does-not-exist"))
    assert response.ok is False
    assert response.code == "unknown_command"
    assert response.exit_code == 1
    assert json.loads(response.to_json())["protocol"] == COMMAND_PROTOCOL


@pytest.mark.parametrize("args", [None, "shell", {"shell": True}, ["shell", 1]])
def test_socket_invalid_args_return_structured_json_error(args):
    server = NIEPSocketServer(dispatcher=CommandDispatcher())
    request = {"command": "container", "args": args, "request_id": "invalid-args"}
    assert server._is_interactive_shell(request) is False
    response = server.handle_request(request)
    json.dumps(response)
    assert response["ok"] is False
    assert response["code"] == "invalid_request"


@pytest.mark.parametrize(
    ("command", "args", "code", "message"),
    [
        ("define", [], "invalid_command_args", "WRONG ARGUMENTS AMOUNT - 1 EXPECTED"),
        ("topoup", [], "no_topology", "NO TOPOLOGY DEFINED"),
        ("topodown", [], "no_topology", "NO TOPOLOGY DEFINED"),
        ("topoclean", [], "no_topology", "NO TOPOLOGY DEFINED"),
        ("topodestroy", [], "no_topology", "NO TOPOLOGY DEFINED"),
        ("vm", [], "invalid_command_args", "VM COMMAND EXPECTED"),
        ("vm", ["management"], "invalid_command_args", "WRONG ARGUMENTS AMOUNT - 2 EXPECTED"),
        ("vm", ["ssh"], "invalid_command_args", "WRONG ARGUMENTS AMOUNT - 4 EXPECTED"),
        ("vm", ["missing"], "unknown_command", "UNKNOWN VM COMMAND"),
        ("container", [], "invalid_command_args", "CONTAINER COMMAND EXPECTED"),
        ("container", ["exec"], "invalid_command_args", "CONTAINER EXEC EXPECTS CONTAINER ID AND COMMAND"),
        ("container", ["shell", "id"], "invalid_command_args", "CONTAINER SHELL REQUIRES AN INTERACTIVE CLIENT"),
        ("container", ["missing"], "unknown_command", "UNKNOWN CONTAINER COMMAND"),
        ("vnf", [], "invalid_command_args", "VNF COMMAND EXPECTED"),
        ("vnf", ["management"], "invalid_command_args", "WRONG ARGUMENTS AMOUNT - 2 EXPECTED"),
        ("vnf", ["action"], "invalid_command_args", "VNF ACTION EXPECTS VNF ID AND ACTION"),
        ("vnf", ["script"], "invalid_command_args", "VNF SCRIPT EXPECTS VNF ID, SCRIPT AND OPTIONAL ERROR SCRIPT"),
        ("vnf", ["missing"], "unknown_command", "UNKNOWN VNF COMMAND"),
        ("sfc", [], "invalid_command_args", "SFC COMMAND EXPECTED"),
        ("sfc", ["management"], "invalid_command_args", "WRONG ARGUMENTS AMOUNT - 2 EXPECTED"),
        ("sfc", ["missing"], "unknown_command", "UNKNOWN SFC COMMAND"),
        ("mininet", [], "topology_not_up", "TOPOLOGY IS NOT UP"),
        ("mininet", ["pingall"], "topology_not_up", "TOPOLOGY IS NOT UP"),
        ("mininet", ["cmd", "h1", "echo"], "topology_not_up", "TOPOLOGY IS NOT UP"),
    ],
)
def test_documented_commands_keep_legacy_codes_and_messages(command, args, code, message):
    result = CommandDispatcher().dispatch(command, args)
    assert result.code.value == code
    assert result.message == message


def test_container_exec_exit_code_and_shell_handle_are_out_of_band(monkeypatch):
    dispatcher = CommandDispatcher()
    dispatcher.router._container.service.exec = lambda _container, _command: ServiceResult(
        ok=False,
        code=ResultCode.CONTAINER_EXEC,
        data={"exit_code": 17, "output": "failed"},
        status=17,
    )
    response = dispatcher.dispatch_request(CommandRequest("container", ("exec", "c1", "false")))
    assert response.exit_code == 17
    assert response.data == {"exit_code": 17, "output": "failed"}
    json.dumps(response.to_dict())

    secret_stream = object()
    dispatcher.router._container.service.open_shell = lambda _container, _command: ServiceResult(
        ok=True, code=ResultCode.CONTAINER_SHELL, data=secret_stream
    )
    public = dispatcher.dispatch_request(CommandRequest("container", ("shell", "c1")))
    assert public.ok is False
    assert public.data is None
    assert dispatcher.open_stream("container", ("shell", "c1")).data is secret_stream


def test_socket_shell_sends_json_header_then_bridges_private_stream(monkeypatch):
    dispatcher = CommandDispatcher()
    stream = type("Stream", (), {"close": lambda self: None})()
    dispatcher.open_stream = lambda _command, _args: ServiceResult(
        ok=True, code=ResultCode.CONTAINER_SHELL, data=stream
    )
    bridged = []
    monkeypatch.setattr(
        "niep.interfaces.socket_server.bridge_sockets",
        lambda connection, private_stream: bridged.append((connection, private_stream)),
    )

    class Connection:
        def __init__(self):
            self.sent = []

        def sendall(self, payload):
            self.sent.append(payload)

    connection = Connection()
    NIEPSocketServer(dispatcher=dispatcher)._handle_interactive_shell(
        connection, {"command": "container", "args": ["shell", "c1"]}
    )
    header = json.loads(connection.sent[0].decode().strip())
    assert header["code"] == "container_shell"
    assert "data" not in header
    assert bridged == [(connection, stream)]


@pytest.mark.parametrize("command,args", [("status", []), ("vm", ["list"]), ("container", ["list"]), ("vnf", ["list"]), ("sfc", ["list"])])
def test_cli_socket_use_case_parity(command, args):
    dispatcher = CommandDispatcher()
    request = {"protocol": COMMAND_PROTOCOL, "version": COMMAND_VERSION, "request_id": "parity", "command": command, "args": args}
    direct = dispatcher.dispatch_request(request).to_dict()
    through_socket = NIEPSocketServer(dispatcher=dispatcher).handle_request(request)
    assert through_socket == direct


def test_interfaces_do_not_import_or_dereference_runtime_objects():
    forbidden_imports = ("niep.runtime", "docker", "libvirt", "mininet")
    forbidden_names = {"executor", "NET", "NIEPEXE", "VMEXEC", "CONTAINEREXEC", "VNFEXEC", "SFCEXEC", "controlVNF"}
    for relative in ("niep/interfaces/cli.py", "niep/interfaces/socket_server.py", "niep/interfaces/niepctl.py"):
        tree = ast.parse(Path(relative).read_text())
        imports = []
        names = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")
            elif isinstance(node, ast.Name):
                names.append(node.id)
            elif isinstance(node, ast.Attribute):
                names.append(node.attr)
        assert not any(any(item in module for item in forbidden_imports) for module in imports)
        assert not forbidden_names.intersection(names)
