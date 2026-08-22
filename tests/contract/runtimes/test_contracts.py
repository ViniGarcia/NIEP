from __future__ import annotations

import json
from subprocess import CalledProcessError
from types import SimpleNamespace

from niep.runtime.container_network import ContainerNetworkRuntime
from niep.runtime.contracts import (
    ContainerComputeRuntime,
    ContainerNetworkRuntimeContract,
    ComputeRuntime,
    ImageStore,
    InfrastructureRuntime,
    NetworkRuntime,
    ProcessRuntime,
    RuntimeAdapterFactory,
    TerminalSession,
    VMComputeRuntime,
    VMNetworkRuntimeContract,
)
from niep.runtime.docker import DockerRuntime, NotFound
from niep.runtime.errors import RuntimeFailure
from niep.runtime.infrastructure import InfrastructureRuntime as HostInfrastructureRuntime
from niep.runtime.libvirt import LibvirtRuntime
from niep.runtime.process import SubprocessRuntime
from niep.runtime.terminal_session import SocketTerminalSession
from niep.runtime.vm_image_store import VMImageStore
from niep.runtime.vm_network import VMNetworkRuntime
from niep.runtime.container import Container
from niep.runtime.vm import VM
from niep.runtime.vnf import VNF
from .fakes import (
    FakeComputeRuntime,
    FakeContainerComputeRuntime,
    FakeContainerNetworkRuntime,
    FakeCommandRunner,
    FakeNetworkRuntime,
    FakeProcessRuntime,
    FakeVMComputeRuntime,
    FakeVMImageStore,
    FakeVMNetworkRuntime,
)


def test_real_adapters_satisfy_small_capability_contracts(tmp_path):
    assert isinstance(DockerRuntime(client=object()), ComputeRuntime)
    assert isinstance(LibvirtRuntime(connection=object()), ComputeRuntime)
    assert isinstance(ContainerNetworkRuntime(), NetworkRuntime)
    assert isinstance(VMNetworkRuntime(), NetworkRuntime)
    assert isinstance(VMImageStore(str(tmp_path)), ImageStore)
    assert isinstance(HostInfrastructureRuntime(), InfrastructureRuntime)
    assert isinstance(HostInfrastructureRuntime(), ProcessRuntime)
    assert isinstance(SubprocessRuntime(), ProcessRuntime)
    assert isinstance(SocketTerminalSession(), TerminalSession)
    assert isinstance(FakeComputeRuntime(), ComputeRuntime)
    assert isinstance(FakeNetworkRuntime(), NetworkRuntime)
    assert isinstance(FakeProcessRuntime(), ProcessRuntime)
    assert isinstance(FakeContainerComputeRuntime(), ContainerComputeRuntime)
    assert isinstance(FakeContainerNetworkRuntime(), ContainerNetworkRuntimeContract)
    assert isinstance(FakeVMComputeRuntime(), VMComputeRuntime)
    assert isinstance(FakeVMImageStore(), ImageStore)
    assert isinstance(FakeVMNetworkRuntime(), VMNetworkRuntimeContract)


def test_factory_is_lazy_and_builds_injectable_adapters():
    factory = RuntimeAdapterFactory()
    assert isinstance(factory.docker(client=object()), ComputeRuntime)
    assert isinstance(factory.container_network(), NetworkRuntime)


def test_cleanup_of_absent_image_is_idempotent(tmp_path):
    store = VMImageStore(str(tmp_path))
    assert store.remove("missing") is None
    assert store.remove("missing") is None


def test_runtime_failure_serializes_cause_and_unserializable_context():
    try:
        raise ValueError("broken")
    except ValueError as cause:
        failure = RuntimeFailure(
            "start",
            "container",
            "ct-1",
            cause=cause,
            retryable=True,
            context={"opaque": object(), "secret": b"safe"},
        )

    payload = failure.to_dict()
    assert payload["operation"] == "start"
    assert payload["resource_type"] == "container"
    assert payload["resource_id"] == "ct-1"
    assert payload["retryable"] is True
    assert payload["cause"] == {"type": "ValueError", "message": "broken"}
    json.dumps(payload)


def test_runtime_failure_accepts_legacy_type_keyword_and_cause():
    cause = ValueError("broken")
    bare = RuntimeFailure("x", cause=cause)
    assert bare.cause_info.type == "ValueError"
    failure = RuntimeFailure("start", type="container", id="ct-1", cause=cause)
    assert failure.resource_type == "container"
    assert failure.resource_id == "ct-1"
    assert failure.cause is cause
    assert failure.cause_info.type == "ValueError"


def test_docker_absent_cleanup_is_successful():
    class Containers:
        def get(self, _container_id):
            raise NotFound("missing")

    class Client:
        containers = Containers()

    runtime = DockerRuntime(client=Client())
    assert runtime.remove("missing") is None
    assert runtime.stop("missing") is None


class CommandFake:
    def __init__(self, output=b"", status=0):
        self.output = output
        self.status = status
        self.calls = []

    def run(self, command, **kwargs):
        self.calls.append(("run", command, kwargs))
        return SimpleNamespace(returncode=self.status, stdout=self.output.decode() if isinstance(self.output, bytes) else self.output)

    def call(self, command, **kwargs):
        self.calls.append(("call", command, kwargs))
        return self.status

    def check_output(self, command, **kwargs):
        self.calls.append(("check_output", command, kwargs))
        return self.output

    def sleep(self, seconds):
        self.calls.append(("sleep", seconds))


def test_network_adapters_use_injected_runner_only():
    runner = CommandFake(output=b"bridge\n")
    container_network = ContainerNetworkRuntime(runner=runner)
    vm_network = VMNetworkRuntime(runner=runner)

    assert vm_network.bridge_lines() == ["bridge", ""]
    assert container_network.interface_exists("ct0") is True
    assert any(call[0] == "check_output" for call in runner.calls)
    assert any(call[0] == "call" for call in runner.calls)


def test_network_runtime_failure_from_injected_runner_is_not_wrapped():
    class FailingRunner(CommandFake):
        def run(self, command, **kwargs):
            failure = RuntimeFailure("run", "process", "ip", cause=ValueError("injected"))
            raise failure

    failure_runner = FailingRunner()
    runtime = ContainerNetworkRuntime(runner=failure_runner)
    try:
        runtime.run_checked("attach", "ct0", ["ip"])
    except RuntimeFailure as failure:
        assert failure.cause.args == ("injected",)
        assert failure.operation == "run"
    else:  # pragma: no cover - assertion branch
        raise AssertionError("injected RuntimeFailure was swallowed")


def test_infrastructure_separates_command_runner_from_process_runtime():
    process_runtime = FakeProcessRuntime()
    command_runner = FakeCommandRunner(output=b"bridge name\tbridge id\n")
    infrastructure = HostInfrastructureRuntime(
        runner=command_runner,
        process_runtime=process_runtime,
    )

    assert infrastructure._runner is command_runner
    assert infrastructure._runner is not process_runtime
    process = infrastructure.start(["fake-controller"])
    assert process["running"] is True
    assert process_runtime.calls[0][0] == "start"
    assert infrastructure.interfaces_mapping() == {}
    assert any(call[0] == "check_output" for call in command_runner.calls)

    # Supplying only a lifecycle fake must still leave command execution on a
    # real command adapter (the fake intentionally has no ``call`` method).
    lifecycle_only = HostInfrastructureRuntime(process_runtime=process_runtime)
    assert lifecycle_only._runner is not process_runtime


def test_command_failures_are_typed_and_serializable_at_adapter_boundaries():
    cause = CalledProcessError(
        7,
        ["brctl", "show"],
        output=b"stdout",
        stderr=b"stderr",
    )
    infrastructure = HostInfrastructureRuntime(runner=FakeCommandRunner(error=cause))
    try:
        infrastructure.interfaces_mapping()
    except RuntimeFailure as failure:
        assert failure.cause is cause
        assert failure.operation == "inspect"
        assert failure.resource_type == "host_network"
        assert failure.context["command"] == ["brctl", "show"]
        assert failure.context["returncode"] == 7
        assert failure.retryable is False
        json.dumps(failure.to_dict())
    else:  # pragma: no cover - assertion branch
        raise AssertionError("infrastructure command failure was not normalized")

    vm_network = VMNetworkRuntime(runner=FakeCommandRunner(error=cause))
    try:
        vm_network.bridge_lines()
    except RuntimeFailure as failure:
        assert failure.cause is cause
        assert failure.resource_type == "bridge"
        assert failure.context["returncode"] == 7
    else:  # pragma: no cover - assertion branch
        raise AssertionError("bridge command failure was not normalized")

    try:
        vm_network.management_ip("02:00:00:00:00:01")
    except RuntimeFailure as failure:
        assert failure.cause is cause
        assert failure.resource_type == "management_network"
    else:  # pragma: no cover - assertion branch
        raise AssertionError("ARP command failure was not normalized")


def test_network_command_failures_keep_safe_context_and_retryability():
    cause = OSError("ip command unavailable")
    container_network = ContainerNetworkRuntime(runner=FakeCommandRunner(error=cause))
    try:
        container_network.run_checked("create_veth", "veth0", ["ip", "link"])
    except RuntimeFailure as failure:
        assert failure.cause is cause
        assert failure.resource_type == "interface"
        assert failure.context["command"] == ["ip", "link"]
        assert failure.retryable is True
        json.dumps(failure.to_dict())
    else:  # pragma: no cover - assertion branch
        raise AssertionError("container command failure was not normalized")

    ssh_failure = CalledProcessError(255, ["sshpass", "-p", "secret"])
    vm_network = VMNetworkRuntime(runner=FakeCommandRunner(error=ssh_failure))
    try:
        vm_network.ssh("root", "secret", "192.0.2.1")
    except RuntimeFailure as failure:
        command = failure.to_dict()["context"]["command"]
        assert command[2] == "<redacted>"
        assert failure.retryable is False
    else:  # pragma: no cover - assertion branch
        raise AssertionError("SSH command failure was not normalized")


def test_process_and_terminal_injected_failures_preserve_identity():
    expected = RuntimeFailure("start", "process", "p", cause=ValueError("injected"))

    from niep.runtime.process import SubprocessRuntime

    process_runtime = SubprocessRuntime(process_factory=lambda *_args, **_kwargs: (_ for _ in ()).throw(expected))
    try:
        process_runtime.start(["false"])
    except RuntimeFailure as failure:
        assert failure is expected
    else:  # pragma: no cover - assertion branch
        raise AssertionError("process RuntimeFailure was wrapped")

    session = SocketTerminalSession(opener=lambda: (_ for _ in ()).throw(expected))
    try:
        session.open_stream()
    except RuntimeFailure as failure:
        assert failure is expected
    else:  # pragma: no cover - assertion branch
        raise AssertionError("terminal RuntimeFailure was wrapped")

    class FailingClose:
        def close(self):
            raise expected

    session = SocketTerminalSession(stream=FailingClose())
    try:
        session.close()
    except RuntimeFailure as failure:
        assert failure is expected
    else:  # pragma: no cover - assertion branch
        raise AssertionError("terminal close RuntimeFailure was wrapped")


def test_docker_and_libvirt_injected_failures_preserve_identity():
    expected = RuntimeFailure("connect", "runtime", "fake", cause=ValueError("injected"))
    docker = DockerRuntime(client_factory=lambda **_kwargs: (_ for _ in ()).throw(expected))
    try:
        docker.get_client()
    except RuntimeFailure as failure:
        assert failure is expected
    else:  # pragma: no cover - assertion branch
        raise AssertionError("Docker RuntimeFailure was wrapped")

    libvirt = LibvirtRuntime(connection_factory=lambda *_args: (_ for _ in ()).throw(expected))
    try:
        libvirt.get_connection()
    except RuntimeFailure as failure:
        assert failure is expected
    else:  # pragma: no cover - assertion branch
        raise AssertionError("libvirt RuntimeFailure was wrapped")


def test_container_flow_uses_minimal_injected_contract_fakes(tmp_path):
    descriptor = tmp_path / "container.json"
    descriptor.write_text(
        json.dumps({
            "ID": "fake-container",
            "IMAGE": "example:latest",
            "COMMAND": ["sleep", "infinity"],
            "INTERFACES": [],
        }),
        encoding="utf-8",
    )
    compute = FakeContainerComputeRuntime()
    network = FakeContainerNetworkRuntime()
    container = Container(str(descriptor), runtime=compute, network=network)

    assert container.upContainer() == 0
    assert container.CONTAINER_STATUS == 0
    assert any(call[0] == "setup_interfaces" for call in network.calls)
    assert container.cleanupContainer() == 0
    assert any(call[0] == "remove" for call in compute.calls)


def test_vm_flow_uses_minimal_injected_contract_fakes(tmp_path):
    descriptor = tmp_path / "vm.json"
    descriptor.write_text(
        json.dumps({
            "ID": "fake-vm",
            "MEMORY": 128,
            "VCPU": 1,
            "DISK": "tinycore12",
            "MANAGEMENT_MAC": "02:00:00:00:00:01",
            "INTERFACES": [],
        }),
        encoding="utf-8",
    )
    compute = FakeVMComputeRuntime()
    image_store = FakeVMImageStore()
    network = FakeVMNetworkRuntime()
    vm = VM(str(descriptor), "fake-vm", [], runtime=compute, image_store=image_store, network=network)
    vm.VM_EXIST = True

    assert vm.upVM() == 0
    assert compute.calls[0][0] == "define_and_create"
    assert vm.cleanupVM() == 0
    assert any(call[0] == "release_interfaces" for call in network.calls) is False


def test_typed_cleanup_records_survive_container_vm_vnf_layers():
    typed = RuntimeFailure(
        "release_interfaces",
        "veth_interface",
        "veth0",
        cause=ValueError("cleanup failed"),
        retryable=True,
        context={"attempt": 2, "opaque": object()},
    )

    container = object.__new__(Container)
    container.ID = "typed-container"
    container.INTERFACES = [{"ID": "veth0"}]
    container.NETWORK = type("Network", (), {"release_interfaces": lambda self, _interfaces: (_ for _ in ()).throw(typed)})()
    container.RUNTIME = type("Runtime", (), {"remove": lambda self, _resource: None})()
    container.CONTAINER = object()
    container.CLEANUP_ERRORS = []
    container.DETAIL = ""
    container.CONTAINER_STATUS = 0

    assert container.cleanupContainer() == -10
    record = container.CLEANUP_ERRORS[0]
    assert record["cause"] == {"type": "ValueError", "message": "cleanup failed"}
    assert record["context"]["attempt"] == 2
    assert record["retryable"] is True
    json.dumps(container.CLEANUP_ERRORS)

    vm = object.__new__(VM)
    vm.ID = "typed-vm"
    vm.VIRT_VM = None
    vm.VM_UP = True
    vm.INTERFACES = []
    vm.RUNTIME = type(
        "FailingVMRuntime",
        (),
        {"exists": lambda self, _resource: (_ for _ in ()).throw(typed)},
    )()
    vm.NETWORK = object()
    vm.CLEANUP_ERRORS = []
    assert vm.cleanupVM() == -10
    assert vm.CLEANUP_ERRORS[0]["cause"] == {"type": "ValueError", "message": "cleanup failed"}
    assert vm.CLEANUP_ERRORS[0]["context"]["attempt"] == 2
    assert vm.CLEANUP_ERRORS[0]["retryable"] is True
    json.dumps(vm.CLEANUP_ERRORS)

    class TypedVM:
        CLEANUP_ERRORS = []

        def cleanupVM(self):
            self.CLEANUP_ERRORS = [typed.to_dict()]
            return -10

    vnf = object.__new__(VNF)
    vnf.ID = "typed-vnf"
    vnf.VNF_UP = True
    vnf.VNF_OPERATOR = object()
    vnf.CLEANUP_ERRORS = []
    vnf.DETAIL = ""
    vnf.VM = TypedVM()
    assert vnf.cleanupVNF() == -10
    assert vnf.CLEANUP_ERRORS[0]["cause"] == {"type": "ValueError", "message": "cleanup failed"}
    assert vnf.CLEANUP_ERRORS[0]["context"]["attempt"] == 2
    assert vnf.CLEANUP_ERRORS[0]["retryable"] is True
    json.dumps(vnf.CLEANUP_ERRORS)


def test_vm_ssh_normalizes_nonzero_legacy_status_and_preserves_typed_failure():
    vm = object.__new__(VM)
    vm.ID = "ssh-vm"
    vm.VM_STATUS = 0
    vm.VM_UP = True
    vm.MANAGEMENT_MAC = "02:00:00:00:00:01"
    vm.managementVM = lambda: "192.0.2.10"

    vm.NETWORK = type("NonzeroSSH", (), {"ssh": lambda self, *_args: 255})()
    try:
        vm.sshVM("root", "secret")
    except RuntimeFailure as failure:
        assert failure.operation == "ssh"
        assert failure.resource_type == "vm"
        assert failure.resource_id == "ssh-vm"
        assert failure.context["legacy_status"] == 255
    else:  # pragma: no cover - assertion branch
        raise AssertionError("nonzero SSH status escaped as an untyped return")

    expected = RuntimeFailure("ssh", "vm", "ssh-vm", cause=OSError("injected"))
    vm.NETWORK = type(
        "FailingSSH",
        (),
        {"ssh": lambda self, *_args: (_ for _ in ()).throw(expected)},
    )()
    try:
        vm.sshVM("root", "secret")
    except RuntimeFailure as failure:
        assert failure is expected
    else:  # pragma: no cover - assertion branch
        raise AssertionError("typed SSH failure was wrapped")
