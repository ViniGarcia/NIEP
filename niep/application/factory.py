"""Explicit materialization boundary for topology runtime objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from niep.domain.spec import TopologySpec


class _MutableInterface(dict):
    """Runtime-owned copy of an immutable interface value object."""

    def __init__(self, spec):
        super().__init__(spec.to_dict() if hasattr(spec, "to_dict") else dict(spec))


class _MutableMininetHost:
    def __init__(self, spec):
        self.ID = spec.ID
        self.INTERFACES = [_MutableInterface(item) for item in spec.INTERFACES]
        self.ELEM = None


class _MutableMininetSwitch:
    def __init__(self, spec):
        self.ID = spec.ID
        self.ELEM = None


class _MutableMininetController:
    def __init__(self, spec):
        self.ID = spec.ID
        self.IP = spec.IP
        self.PORT = spec.PORT
        self.ELEM = None


class _MutableMininetOVSSwitch:
    def __init__(self, spec):
        self.ID = spec.ID
        self.CONTROLLER = spec.CONTROLLER
        self.ELEM = None


@dataclass
class RuntimeConfiguration:
    """Compatibility configuration consumed by the legacy executor."""

    STATUS: int = 0
    DETAIL: str = ""
    SPEC: TopologySpec | None = None


class RuntimeFactory:
    """Create runtime adapters only when the application explicitly asks.

    Importing this module is host-safe. Optional runtime modules are imported
    inside the individual constructors, which also makes this class easy to
    test with injected fakes.
    """

    def __init__(self, runtime_types: Mapping[str, Any] | None = None):
        self.runtime_types = dict(runtime_types or {})

    def _type(self, name: str):
        if name in self.runtime_types:
            return self.runtime_types[name]
        if name == "VM":
            from niep.runtime.vm import VM
            return VM
        if name == "VNF":
            from niep.runtime.vnf import VNF
            return VNF
        if name == "Container":
            from niep.runtime.container import Container
            return Container
        if name == "SFC":
            from niep.runtime.sfc import SFC
            return SFC
        raise KeyError(name)

    def create_vm(self, spec):
        return self._type("VM")(spec.path, None, None)

    def create_vnf(self, spec):
        return self._type("VNF")(spec.path, None)

    def create_container(self, spec):
        return self._type("Container")(spec.path)

    def create_sfc(self, spec, vnf_instances=()):
        """Materialize an SFC from its validated spec and VNF instances.

        The legacy constructor reparses ``SFC_JSON`` and consequently loses
        descriptor-relative path resolution when the process cwd changes.
        Runtime SFCs expose ``from_spec``/``configure`` for this boundary;
        the constructor fallback keeps injected legacy doubles compatible.
        """

        sfc_type = self._type("SFC")
        from_spec = getattr(sfc_type, "from_spec", None)
        if callable(from_spec):
            return from_spec(spec, tuple(vnf_instances))

        try:
            runtime = sfc_type(spec.path)
        except TypeError:
            runtime = sfc_type()
        configure = getattr(runtime, "configure", None)
        if callable(configure):
            configure(spec, tuple(vnf_instances))
            return runtime

        data = spec.to_dict()
        runtime.ID = spec.id
        runtime.SFC_JSON = spec.path
        runtime.VNFS = data["VNFS"]
        runtime.IP = data["IP"]
        runtime.OPS = data["OPS"]
        runtime.CONNECTIONS = data["CONNECTIONS"]
        runtime.SFC_VNF_INSTANCES = list(vnf_instances)
        prepare = getattr(runtime, "prepareSFC", None)
        if callable(prepare) and not getattr(runtime, "SFC_VNFS_CONF", None):
            prepare()
        return runtime

    @staticmethod
    def create_host(spec):
        return _MutableMininetHost(spec)

    @staticmethod
    def create_switch(spec):
        return _MutableMininetSwitch(spec)

    @staticmethod
    def create_controller(spec):
        return _MutableMininetController(spec)

    @staticmethod
    def create_ovs_switch(spec):
        return _MutableMininetOVSSwitch(spec)

    def materialize(self, spec: TopologySpec) -> RuntimeConfiguration:
        """Materialize all sections into a legacy executor configuration."""

        if not isinstance(spec, TopologySpec):
            raise TypeError("RuntimeFactory.materialize expects a TopologySpec")
        result = RuntimeConfiguration(SPEC=spec)
        result.ID = spec.id
        result.VMS = [self.create_vm(item) for item in spec.vms]
        result.VNFS = [self.create_vnf(item) for item in spec.vnfs]
        vnf_instances = {
            item.id: runtime
            for item, runtime in zip(spec.vnfs, result.VNFS)
        }
        result.SFCS = []
        for sfc_spec in spec.sfcs:
            nested_instances = []
            for reference in sfc_spec.vnfs:
                vnf_id = reference.get("ID") if isinstance(reference, Mapping) else None
                if vnf_id not in vnf_instances:
                    raise ValueError(
                        "SFC references an unmaterialized VNF: " + str(vnf_id)
                    )
                nested_instances.append(vnf_instances[vnf_id])
            result.SFCS.append(self.create_sfc(sfc_spec, nested_instances))
        result.CONTAINERS = [self.create_container(item) for item in spec.containers]
        # Domain specs are frozen value objects. The executor attaches Mininet
        # handles and interface elements, so it receives explicit mutable
        # runtime-owned copies instead of mutating the parsed specification.
        result.MNHOSTS = [self.create_host(item) for item in spec.mininet_hosts]
        result.MNSWITCHES = [self.create_switch(item) for item in spec.mininet_switches]
        result.MNCONTROLLER = [self.create_controller(item) for item in spec.mininet_controllers]
        result.MNOVSES = [self.create_ovs_switch(item) for item in spec.mininet_ovs_switches]
        result.CONNECTIONS = [item.to_dict() for item in spec.connections]
        return result

    build = materialize
    from_spec = materialize
    materialize_topology = materialize
    create_topology = materialize
