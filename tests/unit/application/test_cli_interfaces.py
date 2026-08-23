from dataclasses import dataclass, field

import pytest

from niep.domain.result import ResultCode, ServiceResult
from niep.interfaces.cli import NIEPCLI


@dataclass
class FakeCommandPort:
    defined: bool = True
    up: bool = True
    resources: dict[str, list[str]] = field(
        default_factory=lambda: {
            "vm": ["vm1"],
            "container": ["container1"],
            "vnf": ["vnf1"],
            "sfc": ["sfc1"],
        }
    )
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def dispatch(self, command, args=None):
        args = tuple(args or ())
        self.calls.append((command, args))
        if command == "status":
            return ServiceResult(
                ok=True,
                code=ResultCode.STATUS,
                data={"defined": self.defined, "up": self.up},
            )
        if command in self.resources and args == ("list",):
            return ServiceResult(ok=True, code=ResultCode.DEFINED, data=self.resources[command])
        return ServiceResult(ok=False, code=ResultCode.UNKNOWN_COMMAND, message="UNKNOWN COMMAND")

    def vnf_actions(self, _vnf_id):
        self.calls.append(("vnf_actions", ()))
        return ServiceResult(
            ok=True,
            code=ResultCode.VNF_ACTION,
            data={"POST_START": "start", "POST_FUNCTION": "function"},
        )


@pytest.mark.parametrize(
    ("method", "aggregate", "resource_id", "attribute", "prompt"),
    [
        ("do_vm", "vm", "vm1", "VM_ID", "vm(vm1)> "),
        ("do_container", "container", "container1", "CONTAINER_ID", "container(container1)> "),
        ("do_vnf", "vnf", "vnf1", "VNF_ID", "vnf(vnf1)> "),
        ("do_sfc", "sfc", "sfc1", "SFC_ID", "sfc(sfc1)> "),
    ],
)
def test_legacy_cli_selects_resource_via_list_use_case(
    method, aggregate, resource_id, attribute, prompt
):
    cli = NIEPCLI()
    port = FakeCommandPort()
    cli.dispatcher = port

    getattr(cli, method)(resource_id)

    assert getattr(cli, attribute) == resource_id
    assert cli.prompt == prompt
    assert (aggregate, ("list",)) in port.calls
    assert not any(args == (resource_id,) for command, args in port.calls if command == aggregate)


@pytest.mark.parametrize("method", ["do_vm", "do_container", "do_vnf", "do_sfc"])
@pytest.mark.parametrize("args", ["", "one two"])
def test_legacy_cli_rejects_non_single_resource_argument(method, args, capsys):
    cli = NIEPCLI()
    cli.dispatcher = FakeCommandPort()

    getattr(cli, method)(args)

    assert "WRONG ARGUMENTS AMOUNT - 1 ARGUMENT EXPECTED" in capsys.readouterr().out


@pytest.mark.parametrize("method", ["do_vm", "do_container", "do_vnf", "do_sfc"])
def test_legacy_cli_preserves_topology_state_messages(method, capsys):
    cli = NIEPCLI()
    port = FakeCommandPort(defined=False)
    cli.dispatcher = port
    getattr(cli, method)("resource")
    assert capsys.readouterr().out.strip() == "NO TOPOLOGY DEFINED"

    cli = NIEPCLI()
    port = FakeCommandPort(defined=True, up=False)
    cli.dispatcher = port
    getattr(cli, method)("resource")
    assert capsys.readouterr().out.strip() == "TOPOLOGY IS NOT UP"


def test_vnf_action_completion_uses_catalog_port_not_action_dispatch():
    cli = NIEPCLI()
    port = FakeCommandPort()
    cli.dispatcher = port
    cli.VNF_ID = "vnf1"

    assert cli.complete_vnfaction("", "vnfaction ", 0, 0) == ["POST_FUNCTION", "POST_START"]
    assert ("vnf_actions", ()) in port.calls
    assert not any(command == "vnf" and args[:2] == ("action", "vnf1") for command, args in port.calls)


def test_resource_completions_are_empty_when_topology_is_not_ready():
    cli = NIEPCLI()
    cli.dispatcher = FakeCommandPort(defined=False)
    assert cli.complete_vm("", "vm ", 0, 0) == []
    assert cli.complete_container("", "container ", 0, 0) == []
    assert cli.complete_vnf("", "vnf ", 0, 0) == []
    assert cli.complete_sfc("", "sfc ", 0, 0) == []

    cli = NIEPCLI()
    cli.dispatcher = FakeCommandPort(defined=True, up=True, resources={"vm": []})
    assert cli.complete_vm("", "vm ", 0, 0) == ["list"]
