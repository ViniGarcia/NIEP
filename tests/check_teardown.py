#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.support import install_optional_dependency_stubs

install_optional_dependency_stubs()
sys.path.insert(0, str(ROOT / "TOPO-MAN"))
sys.path.insert(0, str(ROOT / "VEM"))


def install_import_stubs():
    if "Parser" not in sys.modules:
        parser = types.ModuleType("Parser")
        parser.PlatformParser = object
        sys.modules["Parser"] = parser

    if "DockerRuntime" not in sys.modules:
        docker_runtime = types.ModuleType("DockerRuntime")

        class DockerRuntimeError(RuntimeError):
            pass

        docker_runtime.DockerRuntimeError = DockerRuntimeError
        docker_runtime.DEFAULT_DOCKER_RUNTIME = object()
        sys.modules["DockerRuntime"] = docker_runtime

    try:
        mininet_available = importlib.util.find_spec("mininet") is not None
    except ValueError:
        mininet_available = "mininet" in sys.modules
    if not mininet_available:
        mininet = types.ModuleType("mininet")
        net = types.ModuleType("mininet.net")
        node = types.ModuleType("mininet.node")
        link = types.ModuleType("mininet.link")
        clean = types.ModuleType("mininet.clean")

        net.Mininet = object
        node.Host = object
        node.Switch = object
        node.OVSSwitch = object
        node.Controller = object
        node.RemoteController = object
        link.Link = object
        link.Intf = object
        clean.Cleanup = object

        sys.modules["mininet"] = mininet
        sys.modules["mininet.net"] = net
        sys.modules["mininet.node"] = node
        sys.modules["mininet.link"] = link
        sys.modules["mininet.clean"] = clean


install_import_stubs()

from Executer import Executer  # noqa: E402
from Container import Container  # noqa: E402
from Command import CommandDispatcher  # noqa: E402
from InfrastructureRuntime import InfrastructureRuntime  # noqa: E402
from VM import VM  # noqa: E402
from VNF import VNF  # noqa: E402
import Service as service_module  # noqa: E402
from Service import TopologyService  # noqa: E402


STAGES = [
    "mininet",
    "ovs",
    "controller",
    "switch",
    "pox",
    "infrastructure",
    "container",
    "vnf",
    "vm",
    "sfc",
]

ERROR_CONTEXT = {
    "mininet": ("mininet", "teardown-test", "stop"),
    "ovs": ("ovs_switch", "ovs1", "stop"),
    "controller": ("controller", "controller1", "stop"),
    "switch": ("switch", "switch1", "stop"),
    "pox": ("process", "pox", "stop_process"),
    "infrastructure": ("infrastructure", "global", "cleanup_topology_infrastructure"),
    "container": ("container", "container1", "downContainer"),
    "vnf": ("vnf", "vnf1", "downVNF"),
    "vm": ("vm", "vm1", "downVM"),
    "sfc": ("sfc", "sfc1", "mark_down"),
}


class Recorder:
    def __init__(self, failures=None):
        self.calls = []
        self.failures = dict(failures or {})

    def call(self, stage):
        self.calls.append(stage)
        remaining = self.failures.get(stage, 0)
        if remaining:
            self.failures[stage] = remaining - 1
            raise RuntimeError("boom-" + stage)
        return 0


class FakeNet:
    def __init__(self, recorder):
        self.recorder = recorder

    def stop(self):
        return self.recorder.call("mininet")


class FakeElement:
    def __init__(self, recorder, stage):
        self.recorder = recorder
        self.stage = stage

    def stop(self):
        return self.recorder.call(self.stage)


class FakeElementSpec:
    def __init__(self, element):
        self.ELEM = element


class FakeInfrastructure:
    def __init__(self, recorder):
        self.recorder = recorder
        self.CLEANUP_ERRORS = []

    def stop_process(self, process):
        return self.recorder.call("pox")

    def cleanup_topology_infrastructure(self):
        return self.recorder.call("infrastructure")


class FakeResource:
    def __init__(self, resource_id, recorder, stage):
        self.ID = resource_id
        self.recorder = recorder
        self.stage = stage
        self.DETAIL = ""
        self.CLEANUP_ERRORS = []

    def _cleanup(self):
        return self.recorder.call(self.stage)

    def cleanupContainer(self):
        return self._cleanup()

    def downContainer(self):
        return self._cleanup()

    def cleanupVNF(self):
        return self._cleanup()

    def downVNF(self):
        return self._cleanup()

    def cleanupVM(self):
        return self._cleanup()

    def downVM(self):
        return self._cleanup()


class FakeSFC:
    def __init__(self, recorder):
        self.ID = "sfc1"
        self.recorder = recorder
        self._up = True

    @property
    def SFC_UP(self):
        return self._up

    @SFC_UP.setter
    def SFC_UP(self, value):
        self.recorder.call("sfc")
        self._up = value


class FakeConfiguration:
    STATUS = 0
    ID = "teardown-test"

    def __init__(self, sfc):
        self.SFCS = [sfc]


def build_executor(failures=None):
    recorder = Recorder(failures)
    sfc = FakeSFC(recorder)
    executor = Executer(FakeConfiguration(sfc))
    executor.NET = FakeNet(recorder)
    executor.OVSSWITCHES = {
        "ovs1": FakeElementSpec(FakeElement(recorder, "ovs")),
    }
    executor.CONTROLLERS = {
        "controller1": FakeElementSpec(FakeElement(recorder, "controller")),
    }
    executor.SWITCHES = {
        "switch1": FakeElementSpec(FakeElement(recorder, "switch")),
    }
    executor.POX = object()
    executor.INFRASTRUCTURE = FakeInfrastructure(recorder)
    executor.CONTAINERS = {
        "container1": FakeResource("container1", recorder, "container"),
    }
    executor.VNFS = {
        "vnf1": FakeResource("vnf1", recorder, "vnf"),
    }
    executor.VMS = {
        "vm1": FakeResource("vm1", recorder, "vm"),
    }
    executor.STATUS = 0
    executor.CLEANUP_REQUIRED = True
    return executor, recorder


def assert_error(error, expected, stage):
    actual = (
        error["resource_type"],
        error["resource_id"],
        error["operation"],
    )
    if actual != expected:
        raise AssertionError("unexpected cleanup context: " + repr(error))
    if error["message"] != "boom-" + stage:
        raise AssertionError("original error was not preserved: " + repr(error))


def check_each_stage_is_best_effort():
    for stage in STAGES:
        executor, recorder = build_executor({stage: 1})
        result = executor.topologyDown()
        if result != -10 or executor.STATUS != -10 or not executor.CLEANUP_REQUIRED:
            raise AssertionError("failure was reported as successful for " + stage)
        if recorder.calls != STAGES:
            raise AssertionError(
                "cleanup stopped after " + stage + ": " + repr(recorder.calls)
            )
        if len(executor.CLEANUP_ERRORS) != 1:
            raise AssertionError(repr(executor.CLEANUP_ERRORS))
        assert_error(executor.CLEANUP_ERRORS[0], ERROR_CONTEXT[stage], stage)


def check_multiple_failures_are_aggregated():
    executor, recorder = build_executor({"controller": 1, "container": 1, "vm": 1})
    result = executor.topologyDown()
    if result != -10 or recorder.calls != STAGES:
        raise AssertionError("multi-failure cleanup was not best-effort")
    if [error["resource_type"] for error in executor.CLEANUP_ERRORS] != [
        "controller",
        "container",
        "vm",
    ]:
        raise AssertionError(repr(executor.CLEANUP_ERRORS))
    for stage, error in zip(("controller", "container", "vm"), executor.CLEANUP_ERRORS):
        assert_error(error, ERROR_CONTEXT[stage], stage)


def check_numeric_cleanup_status_is_a_failure():
    executor, _ = build_executor()
    container = executor.CONTAINERS["container1"]
    container.cleanupContainer = lambda: -7
    container.DETAIL = "adapter refused cleanup"
    result = executor.topologyDown()
    if result != -10 or not executor.CLEANUP_ERRORS:
        raise AssertionError("numeric cleanup failure was reported as success")
    error = executor.CLEANUP_ERRORS[0]
    if error["resource_type"] != "container" or error["message"] != "adapter refused cleanup":
        raise AssertionError(repr(executor.CLEANUP_ERRORS))


def check_legacy_cleanup_errors_are_not_split_or_dropped():
    executor, _ = build_executor()
    container = executor.CONTAINERS["container1"]
    container.CLEANUP_ERRORS = "legacy cleanup failure"

    def fail_cleanup():
        raise RuntimeError("adapter raised")

    container.cleanupContainer = fail_cleanup
    if executor.topologyDown() != -10:
        raise AssertionError("legacy cleanup failure was reported as success")
    if executor.CLEANUP_ERRORS[0]["message"] != "legacy cleanup failure":
        raise AssertionError(repr(executor.CLEANUP_ERRORS))
    if len(executor.CLEANUP_ERRORS) != 2:
        raise AssertionError("legacy cleanup message was split into multiple errors")

    service = TopologyService()
    scalar = service._structuredCleanupErrors(7)
    if len(scalar) != 1 or scalar[0]["message"] != "7":
        raise AssertionError(repr(scalar))


def check_retry_only_repeats_pending_cleanup():
    executor, recorder = build_executor({"container": 1})
    if executor.topologyDown() != -10:
        raise AssertionError("first cleanup unexpectedly succeeded")
    if executor.topologyDown() != 0:
        raise AssertionError("cleanup retry did not succeed")
    if executor.STATUS is not None or executor.CLEANUP_REQUIRED or executor.CLEANUP_ERRORS:
        raise AssertionError("successful retry left a failed cleanup state")
    if recorder.calls != STAGES + ["container"]:
        raise AssertionError("completed cleanup stages were repeated: " + repr(recorder.calls))


def check_rollback_uses_the_teardown_plan():
    executor, recorder = build_executor({"vm": 1})
    executor.STATUS = -5
    errors = executor.rollbackFailedStart()
    if recorder.calls != STAGES or len(errors) != 1:
        raise AssertionError("rollback diverged from teardown: " + repr(recorder.calls))
    assert_error(errors[0], ERROR_CONTEXT["vm"], "vm")


def check_down_and_clean_preserve_executor_on_failure():
    executor, _ = build_executor({"container": 1})
    service = TopologyService()
    service.executor = executor

    down = service.down()
    if down.ok or down.code.value != "topology_down_failed":
        raise AssertionError(down.to_dict())
    if service.executor is not executor:
        raise AssertionError("down discarded the executor after partial cleanup")
    if down.data != {"errors": executor.CLEANUP_ERRORS}:
        raise AssertionError(down.to_dict())

    clean = service.clean()
    if not clean.ok or service.executor is not None:
        raise AssertionError("clean retry did not discard a fully cleaned executor")

    executor, _ = build_executor({"vm": 1})
    service.executor = executor
    clean = service.clean()
    if clean.ok or service.executor is not executor:
        raise AssertionError("clean reported success or discarded a failed executor")


def check_dispatcher_propagates_cleanup_failure():
    executor, _ = build_executor({"switch": 1})
    service = TopologyService()
    service.executor = executor
    dispatcher = CommandDispatcher(service)

    result = dispatcher.dispatch("topoclean")
    if result.ok or result.code.value != "topology_down_failed":
        raise AssertionError(result.to_dict())
    if dispatcher.topology.executor is not executor:
        raise AssertionError("dispatcher lost the executor after cleanup failure")

    retry = dispatcher.dispatch("topoclean")
    if not retry.ok or retry.code.value != "topology_clean":
        raise AssertionError(retry.to_dict())


def check_destroy_gates_persistent_state_on_teardown():
    executor, _ = build_executor({"infrastructure": 1})
    service = TopologyService()
    service.executor = executor
    removed = []
    originalExists = service_module.exists
    originalRmtree = service_module.rmtree
    service_module.exists = lambda path: True
    service_module.rmtree = lambda path: removed.append(path)
    try:
        result = service.destroy()
        if result.ok or result.code.value != "topology_down_failed":
            raise AssertionError(result.to_dict())
        if removed:
            raise AssertionError("destroy removed persistent state before teardown succeeded")
        if service.executor is not executor:
            raise AssertionError("destroy discarded the executor after teardown failure")

        retry = service.destroy()
        if not retry.ok or retry.code.value != "topology_destroyed":
            raise AssertionError(retry.to_dict())
        if len(removed) != 2 or service.executor is not None:
            raise AssertionError("destroy retry did not remove VM/VNF state")
    finally:
        service_module.exists = originalExists
        service_module.rmtree = originalRmtree


def check_destroy_reports_persistent_state_failures():
    executor, _ = build_executor()
    service = TopologyService()
    service.executor = executor
    calls = []
    failures = [RuntimeError("image-busy")]
    originalExists = service_module.exists
    originalRmtree = service_module.rmtree
    service_module.exists = lambda path: True

    def remove(path):
        calls.append(path)
        if failures:
            raise failures.pop()

    service_module.rmtree = remove
    try:
        result = service.destroy()
        if result.ok or service.executor is not executor:
            raise AssertionError("persistent-state failure was reported as success")
        error = result.data["errors"][0]
        if error["operation"] != "remove_persistent_state" or error["message"] != "image-busy":
            raise AssertionError(result.to_dict())

        retry = service.destroy()
        if not retry.ok or service.executor is not None:
            raise AssertionError("persistent-state cleanup could not be retried")
        if len(calls) != 3:
            raise AssertionError("persistent state retry repeated a successful removal")
    finally:
        service_module.exists = originalExists
        service_module.rmtree = originalRmtree


def check_failed_start_preserves_executor_only_when_needed():
    executor, _ = build_executor({"vm": 1})
    executor.STATUS = None

    def fail_start():
        executor.CLEANUP_REQUIRED = True
        raise RuntimeError("startup exploded")

    executor.topologyUp = fail_start
    service = TopologyService()
    service.executor = executor
    result = service.up()
    if result.ok or service.executor is not executor:
        raise AssertionError("failed rollback discarded the executor")
    if not result.data or result.data["errors"][0]["resource_type"] != "vm":
        raise AssertionError(result.to_dict())
    retry = service.clean()
    if not retry.ok or service.executor is not None:
        raise AssertionError("failed-start cleanup could not be retried")

    executor, _ = build_executor()
    executor.STATUS = None

    def fail_start_cleanly():
        executor.CLEANUP_REQUIRED = True
        raise RuntimeError("startup exploded")

    executor.topologyUp = fail_start_cleanly
    service.executor = executor
    result = service.up()
    if result.ok or service.executor is not None:
        raise AssertionError("fully rolled-back startup retained an unnecessary executor")


class FakeContainerNetworkCleanup:
    def __init__(self, failing_interface):
        self.failing_interface = failing_interface
        self.calls = []

    def release_interfaces(self, interfaces):
        interfaceID = interfaces[0]["ID"]
        self.calls.append(interfaceID)
        if interfaceID == self.failing_interface:
            raise RuntimeError("cannot-delete-" + interfaceID)


class FakeContainerRuntimeCleanup:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def remove(self, container_id):
        self.calls.append(container_id)
        if self.fail:
            raise RuntimeError("cannot-remove-" + container_id)


def check_container_cleanup_is_best_effort_per_interface():
    container = object.__new__(Container)
    container.ID = "container-internal"
    container.INTERFACES = [{"ID": "veth0"}, {"ID": "veth1"}]
    container.NETWORK = FakeContainerNetworkCleanup("veth0")
    container.RUNTIME = FakeContainerRuntimeCleanup()
    container.CONTAINER = object()
    container.CLEANUP_ERRORS = []
    container.DETAIL = ""
    container.CONTAINER_STATUS = 0

    result = container.cleanupContainer()
    if result != -10:
        raise AssertionError("veth cleanup failure was reported as success")
    if container.NETWORK.calls != ["veth0", "veth1"]:
        raise AssertionError("one veth failure skipped later interfaces")
    if container.RUNTIME.calls != ["container-internal"]:
        raise AssertionError("one veth failure skipped container removal")
    if container.CLEANUP_ERRORS[0]["resource_type"] != "veth_interface":
        raise AssertionError(repr(container.CLEANUP_ERRORS))


class FakeVMRuntimeCleanup:
    def __init__(self, failures):
        self.failures = set(failures)
        self.calls = []

    def exists(self, vm_id):
        self.calls.append("exists")
        return True

    def lookup(self, vm_id):
        self.calls.append("lookup")
        return object()

    def destroy(self, domain):
        self.calls.append("destroy")
        if "destroy" in self.failures:
            raise RuntimeError("cannot-destroy")

    def undefine(self, domain):
        self.calls.append("undefine")
        if "undefine" in self.failures:
            raise RuntimeError("cannot-undefine")


class FakeVMNetworkCleanup:
    def __init__(self, failing_interface=None):
        self.failing_interface = failing_interface
        self.calls = []

    def release_interfaces(self, interfaces):
        interfaceID = interfaces[0]["ID"]
        self.calls.append(interfaceID)
        if interfaceID == self.failing_interface:
            raise RuntimeError("cannot-release-" + interfaceID)


def check_vm_cleanup_attempts_domain_and_all_interfaces():
    vm = object.__new__(VM)
    vm.ID = "vm-internal"
    vm.VIRT_VM = None
    vm.VM_UP = True
    vm.INTERFACES = [{"ID": "vm-if0"}, {"ID": "vm-if1"}]
    vm.RUNTIME = FakeVMRuntimeCleanup({"destroy"})
    vm.NETWORK = FakeVMNetworkCleanup("vm-if0")
    vm.CLEANUP_ERRORS = []

    result = vm.cleanupVM()
    if result != -10:
        raise AssertionError("VM partial cleanup was reported as success")
    if vm.RUNTIME.calls != ["exists", "lookup", "destroy", "undefine"]:
        raise AssertionError("VM domain operations were not best-effort")
    if vm.NETWORK.calls != ["vm-if0", "vm-if1"]:
        raise AssertionError("one VM interface failure skipped later interfaces")
    if [error["operation"] for error in vm.CLEANUP_ERRORS] != [
        "destroy",
        "release_interfaces",
    ]:
        raise AssertionError(repr(vm.CLEANUP_ERRORS))


class RetryVMRuntimeCleanup:
    def __init__(self):
        self.calls = []
        self.fail_undefine = True

    def exists(self, vm_id):
        self.calls.append("exists")
        return True

    def lookup(self, vm_id):
        self.calls.append("lookup")
        return object()

    def destroy(self, domain):
        self.calls.append("destroy")

    def undefine(self, domain):
        self.calls.append("undefine")
        if self.fail_undefine:
            self.fail_undefine = False
            raise RuntimeError("cannot-undefine-once")


class RetryVMNetworkCleanup:
    def __init__(self):
        self.calls = []
        self.fail_release = True

    def release_interfaces(self, interfaces):
        interface_id = interfaces[0]["ID"]
        self.calls.append(interface_id)
        if self.fail_release:
            self.fail_release = False
            raise RuntimeError("cannot-release-once")


def check_vm_cleanup_retry_skips_completed_domain_operation():
    vm = object.__new__(VM)
    vm.ID = "vm-retry"
    vm.VIRT_VM = None
    vm.VM_UP = True
    vm.INTERFACES = [{"ID": "vm-if0"}]
    vm.RUNTIME = RetryVMRuntimeCleanup()
    vm.NETWORK = RetryVMNetworkCleanup()
    vm.CLEANUP_ERRORS = []

    if vm.cleanupVM() != -10 or vm.cleanupVM() != 0:
        raise AssertionError("VM cleanup retry did not finish")
    if vm.RUNTIME.calls != ["exists", "lookup", "destroy", "undefine", "undefine"]:
        raise AssertionError("VM retry repeated a completed operation")
    if vm.NETWORK.calls != ["vm-if0", "vm-if0"]:
        raise AssertionError("VM retry skipped the pending interface")


class LegacyVNFVMCleanup:
    def __init__(self, errors, raises=False):
        self.CLEANUP_ERRORS = errors
        self.raises = raises

    def cleanupVM(self):
        if self.raises:
            raise RuntimeError("legacy VM cleanup raised")
        return -10


def check_vnf_cleanup_normalizes_legacy_errors():
    vnf = object.__new__(VNF)
    vnf.ID = "vnf-retry"
    vnf.VNF_UP = True
    vnf.VNF_OPERATOR = object()
    vnf.CLEANUP_ERRORS = []
    vnf.DETAIL = ""
    vnf.VM = LegacyVNFVMCleanup("legacy VM cleanup failure")

    if vnf.cleanupVNF() != -10:
        raise AssertionError("VNF cleanup unexpectedly succeeded")
    if len(vnf.CLEANUP_ERRORS) != 1:
        raise AssertionError(repr(vnf.CLEANUP_ERRORS))
    if vnf.CLEANUP_ERRORS[0]["message"] != "legacy VM cleanup failure":
        raise AssertionError(repr(vnf.CLEANUP_ERRORS))

    vnf.VM = LegacyVNFVMCleanup(None, raises=True)
    if vnf.cleanupVNF() != -10:
        raise AssertionError("VNF exception unexpectedly succeeded")
    if len(vnf.CLEANUP_ERRORS) != 1:
        raise AssertionError(repr(vnf.CLEANUP_ERRORS))
    if vnf.CLEANUP_ERRORS[0]["message"] != "legacy VM cleanup raised":
        raise AssertionError(repr(vnf.CLEANUP_ERRORS))


class FakeInfrastructureCleanup(InfrastructureRuntime):
    def __init__(self):
        self.calls = []

    def destroy_virt_network(self, networkID):
        self.calls.append("network")
        raise RuntimeError("cannot-destroy-network")

    def remove_bridge(self, bridgeID):
        self.calls.append("bridge")
        raise RuntimeError("cannot-remove-bridge")


class RetryInfrastructureCleanup(InfrastructureRuntime):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.fail_bridge = True

    def destroy_virt_network(self, networkID):
        self.calls.append("network")

    def remove_bridge(self, bridgeID):
        self.calls.append("bridge")
        if self.fail_bridge:
            self.fail_bridge = False
            raise RuntimeError("cannot-remove-bridge-once")


def check_global_infrastructure_aggregates_subresource_failures():
    infrastructure = FakeInfrastructureCleanup()
    result = infrastructure.cleanup_topology_infrastructure()
    if result != -10 or infrastructure.calls != ["network", "bridge"]:
        raise AssertionError("global infrastructure cleanup stopped early")
    if [error["resource_type"] for error in infrastructure.CLEANUP_ERRORS] != [
        "libvirt_network",
        "bridge",
    ]:
        raise AssertionError(repr(infrastructure.CLEANUP_ERRORS))


def check_global_infrastructure_retry_skips_completed_resource():
    infrastructure = RetryInfrastructureCleanup()
    if infrastructure.cleanup_topology_infrastructure() != -10:
        raise AssertionError("infrastructure failure unexpectedly succeeded")
    if infrastructure.cleanup_topology_infrastructure() != 0:
        raise AssertionError("infrastructure retry did not finish")
    if infrastructure.calls != ["network", "bridge", "bridge"]:
        raise AssertionError("infrastructure retry repeated network cleanup")


class RetryContainerNetworkCleanup:
    def __init__(self):
        self.calls = []
        self.fail_interface = True

    def release_interfaces(self, interfaces):
        interface_id = interfaces[0]["ID"]
        self.calls.append(interface_id)
        if self.fail_interface:
            self.fail_interface = False
            raise RuntimeError("cannot-release-once")


class RetryContainerRuntimeCleanup:
    def __init__(self):
        self.calls = []
        self.fail_remove = True

    def remove(self, container_id):
        self.calls.append(container_id)
        if self.fail_remove:
            self.fail_remove = False
            raise RuntimeError("cannot-remove-once")


def check_container_cleanup_retry_skips_completed_interfaces():
    container = object.__new__(Container)
    container.ID = "container-retry"
    container.INTERFACES = [{"ID": "veth0"}, {"ID": "veth1"}]
    container.NETWORK = RetryContainerNetworkCleanup()
    container.RUNTIME = RetryContainerRuntimeCleanup()
    container.CONTAINER = object()
    container.CLEANUP_ERRORS = []
    container.DETAIL = ""
    container.CONTAINER_STATUS = 0

    if container.cleanupContainer() != -10 or container.cleanupContainer() != 0:
        raise AssertionError("container cleanup retry did not finish")
    if container.NETWORK.calls != ["veth0", "veth1", "veth0"]:
        raise AssertionError("container retry repeated a completed interface")
    if container.RUNTIME.calls != ["container-retry", "container-retry"]:
        raise AssertionError("container retry skipped the pending removal")


def main():
    check_each_stage_is_best_effort()
    check_multiple_failures_are_aggregated()
    check_numeric_cleanup_status_is_a_failure()
    check_legacy_cleanup_errors_are_not_split_or_dropped()
    check_retry_only_repeats_pending_cleanup()
    check_rollback_uses_the_teardown_plan()
    check_down_and_clean_preserve_executor_on_failure()
    check_dispatcher_propagates_cleanup_failure()
    check_destroy_gates_persistent_state_on_teardown()
    check_destroy_reports_persistent_state_failures()
    check_failed_start_preserves_executor_only_when_needed()
    check_container_cleanup_is_best_effort_per_interface()
    check_container_cleanup_retry_skips_completed_interfaces()
    check_vm_cleanup_attempts_domain_and_all_interfaces()
    check_vm_cleanup_retry_skips_completed_domain_operation()
    check_vnf_cleanup_normalizes_legacy_errors()
    check_global_infrastructure_aggregates_subresource_failures()
    check_global_infrastructure_retry_skips_completed_resource()
    print("[ OK ] best-effort topology teardown and retry semantics")


if __name__ == "__main__":
    main()
