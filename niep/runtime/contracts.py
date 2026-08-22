"""Small capability contracts for replaceable runtime adapters.

The protocols intentionally avoid imposing VM-only or container-only
operations on the other implementation.  Legacy adapter names (``lookup``,
``release_interfaces`` and friends) remain available on the concrete classes;
these contracts describe the stable seam used by new code and fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ComputeRuntime(Protocol):
    """Common lifecycle operations shared by compute adapters."""

    def create(self, *args: Any, **kwargs: Any) -> Any: ...

    def start(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...

    def stop(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...

    def remove(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class ContainerComputeRuntime(ComputeRuntime, Protocol):
    """Docker-like compute capability consumed by :class:`Container`."""

    def exists(self, resource_id: Any) -> bool: ...

    def lookup(self, resource_id: Any) -> Any: ...

    def is_running(self, resource_id: Any) -> bool: ...

    def exec(self, resource_id: Any, command: Any) -> Any: ...

    def open_interactive_exec(self, resource_id: Any, command: Any) -> Any: ...


@runtime_checkable
class VMComputeRuntime(ComputeRuntime, Protocol):
    """Libvirt-like compute capability consumed by :class:`VM`."""

    def exists(self, resource_id: Any) -> bool: ...

    def lookup(self, resource_id: Any) -> Any: ...

    def is_running(self, resource_id: Any) -> bool: ...

    def define_and_create(self, resource_id: Any, domain_xml: str) -> Any: ...

    def destroy(self, resource: Any) -> Any: ...

    def undefine(self, resource: Any) -> Any: ...


@runtime_checkable
class NetworkRuntime(Protocol):
    def prepare(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...

    def attach(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...

    def detach(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...

    def cleanup(self, resource: Any, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class ContainerNetworkRuntimeContract(NetworkRuntime, Protocol):
    def setup_interfaces(self, container: Any, interfaces: Any) -> Any: ...

    def release_interfaces(self, interfaces: Any) -> Any: ...

    def interface_exists(self, interface_id: Any) -> bool: ...

    def delete_interface(self, interface_id: Any) -> Any: ...

    def container_pid(self, container: Any) -> str: ...


@runtime_checkable
class VMNetworkRuntimeContract(NetworkRuntime, Protocol):
    def prepare_interfaces(self, interfaces: Any) -> Any: ...

    def release_interfaces(self, interfaces: Any) -> Any: ...

    def bridge_lines(self) -> Any: ...

    def bridge_exists(self, bridge_id: Any) -> bool: ...

    def create_bridge(self, bridge_id: Any, mac: str) -> Any: ...

    def enable_bridge(self, bridge_id: Any) -> Any: ...

    def disable_bridge(self, bridge_id: Any) -> Any: ...

    def delete_bridge(self, bridge_id: Any) -> Any: ...

    def management_ip(self, management_mac: str) -> str | None: ...

    def ssh(self, user: str, passwd: str, management_ip: str) -> Any: ...


@runtime_checkable
class ImageStore(Protocol):
    def validate(self, image: Any, *args: Any, **kwargs: Any) -> Any: ...

    def instantiate(self, image: Any, *args: Any, **kwargs: Any) -> Any: ...

    def remove(self, instance: Any, *args: Any, **kwargs: Any) -> Any: ...

    # VM materialization is also a real image-store capability.  Keeping these
    # names on the contract prevents the VM from reaching around an injected
    # fake to call concrete implementation details.
    def base_disk_exists(self, image: Any) -> bool: ...

    def instance_exists(self, instance: Any) -> bool: ...

    def create_instance(self, instance: Any, image: Any) -> Any: ...

    def remove_instance(self, instance: Any) -> Any: ...

    def base_disk_path(self, image: Any) -> Any: ...

    def template_xml_path(self, image: Any) -> Any: ...

    def instance_path(self, instance: Any) -> Any: ...

    def instance_disk_path(self, instance: Any, image: Any) -> Any: ...

    def instance_xml_path(self, instance: Any, image: Any) -> Any: ...

    def copy_template_xml(self, instance: Any, image: Any) -> Any: ...

    def read_domain_xml(self, instance: Any, image: Any) -> str: ...


@runtime_checkable
class ProcessRuntime(Protocol):
    def start(self, command: Any, *args: Any, **kwargs: Any) -> Any: ...

    def terminate(self, process: Any, *args: Any, **kwargs: Any) -> Any: ...

    def wait(self, process: Any, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class CommandRunner(Protocol):
    """Host command capability injected into network adapters."""

    def run(self, command: Any, *args: Any, **kwargs: Any) -> Any: ...

    def call(self, command: Any, *args: Any, **kwargs: Any) -> int: ...

    def check_output(self, command: Any, *args: Any, **kwargs: Any) -> Any: ...

    def sleep(self, seconds: float) -> Any: ...


@runtime_checkable
class InfrastructureRuntime(Protocol):
    """Exact host capability consumed by ``Executer``."""

    def interfaces_mapping(self) -> Any: ...

    def start_local_pox(self) -> Any: ...

    def stop_process(self, process: Any) -> Any: ...

    def prepare_topology_infrastructure(self) -> Any: ...

    def cleanup_topology_infrastructure(self) -> Any: ...


@runtime_checkable
class InfrastructureLifecycle(Protocol):
    """Small generic lifecycle view for callers that do not need POX."""

    def prepare(self, *args: Any, **kwargs: Any) -> Any: ...

    def cleanup(self, *args: Any, **kwargs: Any) -> Any: ...


@runtime_checkable
class TerminalSession(Protocol):
    def open_stream(self, *args: Any, **kwargs: Any) -> Any: ...

    def close(self, *args: Any, **kwargs: Any) -> Any: ...


# Descriptive alias for callers that want to distinguish the protocol from
# ``niep.runtime.infrastructure.InfrastructureRuntime``.
InfrastructureRuntimeContract = InfrastructureRuntime


@dataclass
class RuntimeDependencies:
    """Optional dependencies accepted by VM/container orchestration objects."""

    compute: ComputeRuntime | None = None
    image_store: ImageStore | None = None
    network: NetworkRuntime | None = None


class RuntimeAdapterFactory:
    """Lazy constructors for concrete runtime adapters.

    Imports happen inside methods so merely importing this module cannot load
    or connect an external runtime.  Callers may subclass or replace any
    method with a deterministic fake factory.
    """

    def docker(self, **kwargs: Any) -> ComputeRuntime:
        from .docker import DockerRuntime

        return DockerRuntime(**kwargs)

    def compute(self, kind: str = "docker", **kwargs: Any) -> ComputeRuntime:
        if kind == "docker":
            return self.docker(**kwargs)
        if kind in ("libvirt", "vm"):
            return self.libvirt(**kwargs)
        raise ValueError("unknown compute runtime: " + str(kind))

    def libvirt(self, **kwargs: Any) -> ComputeRuntime:
        from .libvirt import LibvirtRuntime

        return LibvirtRuntime(**kwargs)

    def container_network(self, **kwargs: Any) -> NetworkRuntime:
        from .container_network import ContainerNetworkRuntime

        return ContainerNetworkRuntime(**kwargs)

    def vm_network(self, **kwargs: Any) -> NetworkRuntime:
        from .vm_network import VMNetworkRuntime

        return VMNetworkRuntime(**kwargs)

    def network(self, kind: str = "vm", **kwargs: Any) -> NetworkRuntime:
        if kind in ("vm", "bridge"):
            return self.vm_network(**kwargs)
        if kind in ("container", "veth"):
            return self.container_network(**kwargs)
        raise ValueError("unknown network runtime: " + str(kind))

    def image_store(self, base_path: str, **kwargs: Any) -> ImageStore:
        from .vm_image_store import VMImageStore

        return VMImageStore(base_path, **kwargs)

    def infrastructure(self, **kwargs: Any) -> InfrastructureRuntime:
        from .infrastructure import InfrastructureRuntime as HostInfrastructureRuntime

        return HostInfrastructureRuntime(**kwargs)

    def process(self, **kwargs: Any) -> ProcessRuntime:
        from .process import SubprocessRuntime

        return SubprocessRuntime(**kwargs)

    def terminal(self, stream=None, opener=None) -> TerminalSession:
        from .terminal_session import SocketTerminalSession

        return SocketTerminalSession(stream=stream, opener=opener)


def default_runtime_factory() -> RuntimeAdapterFactory:
    return RuntimeAdapterFactory()


def legacy_status(value: Any) -> int | Any:
    """Return a numeric legacy status at the compatibility boundary."""

    if value is None or value is True:
        return 0
    if value is False:
        return -1
    return value


normalize_status = legacy_status


__all__ = [
    "ComputeRuntime",
    "CommandRunner",
    "ContainerComputeRuntime",
    "ContainerNetworkRuntimeContract",
    "ImageStore",
    "InfrastructureLifecycle",
    "InfrastructureRuntime",
    "InfrastructureRuntimeContract",
    "NetworkRuntime",
    "ProcessRuntime",
    "RuntimeDependencies",
    "RuntimeAdapterFactory",
    "TerminalSession",
    "VMComputeRuntime",
    "VMNetworkRuntimeContract",
    "legacy_status",
    "normalize_status",
    "default_runtime_factory",
]
