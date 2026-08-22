"""Collectable wrappers for host-safe error and rollback checks."""

from __future__ import annotations

import json
from subprocess import CalledProcessError
from types import SimpleNamespace

import pytest

from tests import check_error_handling
from niep.application.executer import Executer
from niep.application.factory import RuntimeFactory
from niep.application.service import ContainerService, TopologyService, VMService
from niep.paths import NIEPPathError
from niep.runtime.errors import RuntimeFailure
from niep.runtime.infrastructure import InfrastructureRuntime


pytestmark = pytest.mark.contract


def test_parser_diagnostics(tmp_path) -> None:
    check_error_handling.check_parser_diagnostics(tmp_path)


def test_parser_reports_runtime_asset_path_error_without_traceback(tmp_path) -> None:
    """VM materialization failures remain structured parser diagnostics."""

    descriptor = tmp_path / "vm.json"
    descriptor.write_text(
        json.dumps(
            {
                "ID": "vm",
                "MEMORY": 300,
                "VCPU": 1,
                "DISK": "tinycore12",
                "MANAGEMENT_MAC": "52:54:00:00:00:01",
                "INTERFACES": [],
            }
        ),
        encoding="utf-8",
    )
    topology = tmp_path / "topology.json"
    topology.write_text(
        json.dumps(
            {
                "ID": "missing-runtime-asset",
                "VMS": [descriptor.name],
                "VNFS": [],
                "SFCS": [],
                "CONTAINERS": [],
                "MININET": {
                    "HOSTS": [],
                    "SWITCHES": [],
                    "CONTROLLERS": [],
                    "OVSWITCHES": [],
                },
                "CONNECTIONS": [],
            }
        ),
        encoding="utf-8",
    )

    def fail_to_materialize(*args, **kwargs):
        raise NIEPPathError("asset VEM/IMAGES is unavailable")

    service = TopologyService(runtime_factory=RuntimeFactory({"VM": fail_to_materialize}))
    result = service.define(str(topology))

    assert not result.ok
    assert result.status == -3
    assert result.data.ERROR["message"] == (
        "Runtime materialization failed: asset VEM/IMAGES is unavailable"
    )
    assert "Runtime materialization failed" in result.detail


def test_docker_runtime_start_error_is_structured() -> None:
    check_error_handling.check_docker_runtime_start_error()


def test_container_exec_error_is_structured() -> None:
    check_error_handling.check_container_exec_error_result()


def test_container_network_failure_rolls_back(tmp_path) -> None:
    check_error_handling.check_container_network_rollback(tmp_path)


@pytest.mark.integration
@pytest.mark.privileged
def test_failed_topology_start_cleanup_requires_infrastructure(tmp_path) -> None:
    check_error_handling.check_failed_topology_start_cleanup(tmp_path)


def test_cleanup_failure_keeps_runtime_failure_through_service_boundary():
    command_error = CalledProcessError(
        17,
        ["virsh", "net-list", "--name"],
        output=b"network output",
        stderr=b"network stderr",
    )

    class FailingRunner:
        def check_output(self, _command, **_kwargs):
            raise command_error

        def call(self, _command, **_kwargs):
            raise command_error

        def sleep(self, _seconds):
            return None

        def run(self, _command, **_kwargs):
            raise command_error

    infrastructure = InfrastructureRuntime(runner=FailingRunner())
    configuration = SimpleNamespace(STATUS=0, SFCS=[])
    executor = Executer(configuration, infrastructure=infrastructure)
    executor.STATUS = 0
    executor.CLEANUP_REQUIRED = True

    service = TopologyService()
    service.executor = executor
    result = service.clean()

    assert not result.ok
    assert result.code.value == "topology_down_failed"
    payload = result.to_dict()
    json.dumps(result.data)
    json.dumps(payload)
    errors = payload["data"]["errors"]
    assert errors
    network_error = next(item for item in errors if item["resource_type"] == "libvirt_network")
    assert network_error["operation"] == "inspect"
    assert network_error["resource_id"] == "vnNIEP"
    assert network_error["message"] == "command failed while inspecting runtime state"
    assert network_error["cause"]["type"] == "CalledProcessError"
    assert network_error["context"]["returncode"] == 17
    assert network_error["retryable"] is False
    assert network_error == next(
        item for item in executor.CLEANUP_ERRORS if item["resource_type"] == "libvirt_network"
    )


class _TypedServiceTopology:
    def __init__(self, container=None, vm=None):
        self.container = container
        self.vm = vm

    def get_container(self, _container_id):
        return self.container

    def get_vm(self, _vm_id):
        return self.vm


def test_container_service_captures_base_runtime_failure_with_structured_data():
    failure = RuntimeFailure(
        "exec",
        "container",
        "typed-container",
        cause=ValueError("injected exec failure"),
        retryable=True,
        context={"command": ["false"], "opaque": object()},
    )
    container = SimpleNamespace(
        execContainer=lambda _command: (_ for _ in ()).throw(failure),
    )
    result = ContainerService(_TypedServiceTopology(container=container)).exec("typed-container", ["false"])

    assert not result.ok
    assert result.code.value == "container_runtime_error"
    assert result.data["error"] == failure.to_dict()
    json.dumps(result.data)
    json.dumps(result.to_dict())


def test_container_shell_service_captures_base_runtime_failure_with_structured_data():
    failure = RuntimeFailure(
        "shell",
        "container",
        "typed-container",
        cause=ValueError("injected shell failure"),
        retryable=False,
        context={"command": ["sh"]},
    )
    container = SimpleNamespace(
        openShell=lambda _command: (_ for _ in ()).throw(failure),
    )
    result = ContainerService(_TypedServiceTopology(container=container)).open_shell("typed-container", ["sh"])

    assert not result.ok
    assert result.code.value == "container_runtime_error"
    assert result.data["error"] == failure.to_dict()
    json.dumps(result.data)
    json.dumps(result.to_dict())


def test_vm_service_captures_base_runtime_failure_from_ssh():
    failure = RuntimeFailure(
        "ssh",
        "vm",
        "typed-vm",
        cause=OSError("injected SSH failure"),
        retryable=True,
        context={"endpoint": "192.0.2.10"},
    )
    vm = SimpleNamespace(
        sshVM=lambda _user, _passwd: (_ for _ in ()).throw(failure),
    )
    result = VMService(_TypedServiceTopology(vm=vm)).ssh("typed-vm", "root", "secret")

    assert not result.ok
    assert result.code.value == "vm_ssh"
    assert result.data["error"] == failure.to_dict()
    json.dumps(result.data)
    json.dumps(result.to_dict())
