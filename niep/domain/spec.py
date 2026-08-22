"""Immutable, runtime-neutral topology value objects.

The old project exposed dictionaries and mutable runtime instances from its
parser. These objects retain the old upper-case accessors and wire shape, but
contain only descriptor data. Runtime adapters are created by
``niep.application.factory.RuntimeFactory``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


def _freeze(value: Any) -> Any:
    if isinstance(value, MappingProxyType):
        return value
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_freeze(item) for item in value)
    return value


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


@dataclass(frozen=True)
class InterfaceSpec:
    mac: str
    ip: str | None = None
    id: str | None = None
    link_mac: str | None = None
    elem: object = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]):
        return cls(
            id=data.get("ID"), mac=data.get("MAC"), ip=data.get("IP"),
            link_mac=data.get("LINK_MAC"), elem=data.get("ELEM"),
        )

    def to_dict(self):
        data = {"MAC": self.mac, "IP": self.ip}
        if self.id is not None:
            data["ID"] = self.id
        if self.link_mac is not None:
            data["LINK_MAC"] = self.link_mac
        if self.elem is not None:
            data["ELEM"] = self.elem
        return data

    def __contains__(self, key):
        return key in self.to_dict()

    def __getitem__(self, key):
        return self.to_dict()[key]

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


@dataclass(frozen=True)
class MininetHostSpec:
    id: str
    interfaces: tuple[InterfaceSpec, ...] = ()
    elem: object = None

    def __post_init__(self):
        object.__setattr__(self, "interfaces", tuple(self.interfaces or ()))

    @property
    def ID(self): return self.id
    @property
    def INTERFACES(self): return self.interfaces
    @property
    def ELEM(self): return self.elem

    def to_dict(self):
        return {"ID": self.id, "INTERFACES": [item.to_dict() for item in self.interfaces]}


@dataclass(frozen=True)
class VMSpec:
    id: str
    path: str
    memory: int
    vcpu: int
    disk: str
    management_mac: str
    interfaces: tuple[InterfaceSpec, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "interfaces", tuple(self.interfaces or ()))

    @property
    def ID(self): return self.id
    @property
    def VM_JSON(self): return self.path
    @property
    def MEMORY(self): return self.memory
    @property
    def VCPU(self): return self.vcpu
    @property
    def DISK(self): return self.disk
    @property
    def MANAGEMENT_MAC(self): return self.management_mac
    @property
    def INTERFACES(self): return self.interfaces

    def to_dict(self):
        return {"ID": self.id, "MEMORY": self.memory, "VCPU": self.vcpu,
                "DISK": self.disk, "MANAGEMENT_MAC": self.management_mac,
                "INTERFACES": [item.to_dict() for item in self.interfaces]}

    @classmethod
    def from_vm(cls, vm):
        return cls(
            id=vm.ID, path=vm.VM_JSON, memory=vm.MEMORY, vcpu=vm.VCPU,
            disk=vm.DISK, management_mac=vm.MANAGEMENT_MAC,
            interfaces=tuple(InterfaceSpec.from_dict(iface) for iface in vm.INTERFACES),
        )


@dataclass(frozen=True)
class ContainerSpec:
    id: str
    path: str
    image: str
    command: object
    entrypoint: object = None
    privileged: bool = True
    sysctls: Mapping[str, Any] = field(default_factory=dict)
    interfaces: tuple[InterfaceSpec, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, "command", _freeze(self.command))
        object.__setattr__(self, "entrypoint", _freeze(self.entrypoint))
        object.__setattr__(self, "sysctls", _freeze(self.sysctls or {}))
        object.__setattr__(self, "interfaces", tuple(self.interfaces or ()))

    @property
    def ID(self): return self.id
    @property
    def CONTAINER_JSON(self): return self.path
    @property
    def IMAGE(self): return self.image
    @property
    def COMMAND(self): return _thaw(self.command)
    @property
    def ENTRYPOINT(self): return _thaw(self.entrypoint)
    @property
    def PRIVILEGED(self): return self.privileged
    @property
    def SYSCTLS(self): return _thaw(self.sysctls)
    @property
    def INTERFACES(self): return self.interfaces

    def to_dict(self):
        return {"ID": self.id, "IMAGE": self.image, "COMMAND": _thaw(self.command),
                "ENTRYPOINT": _thaw(self.entrypoint), "PRIVILEGED": self.privileged,
                "SYSCTLS": _thaw(self.sysctls),
                "INTERFACES": [item.to_dict() for item in self.interfaces]}

    @classmethod
    def from_container(cls, container):
        return cls(
            id=container.ID, path=container.CONTAINER_JSON, image=container.IMAGE,
            command=container.COMMAND, entrypoint=container.ENTRYPOINT,
            privileged=container.PRIVILEGED, sysctls=container.SYSCTLS,
            interfaces=tuple(InterfaceSpec.from_dict(iface) for iface in container.INTERFACES),
        )


@dataclass(frozen=True)
class VNFSpec:
    id: str
    path: str
    vm_path: str
    vm: VMSpec

    @property
    def ID(self): return self.id
    @property
    def VNF_JSON(self): return self.path
    @property
    def VM(self): return self.vm

    def to_dict(self):
        return {"ID": self.id, "VM": self.vm_path}

    @classmethod
    def from_vnf(cls, vnf):
        return cls(id=vnf.ID, path=vnf.VNF_JSON, vm_path=vnf.VM.VM_JSON,
                   vm=VMSpec.from_vm(vnf.VM))


@dataclass(frozen=True)
class SFCSpec:
    id: str
    path: str
    vnfs: tuple = ()
    ip: Mapping[str, Any] = field(default_factory=dict)
    ops: tuple = ()
    connections: tuple = ()

    def __post_init__(self):
        object.__setattr__(self, "vnfs", _freeze(self.vnfs or ()))
        object.__setattr__(self, "ip", _freeze(self.ip or {}))
        object.__setattr__(self, "ops", _freeze(self.ops or ()))
        object.__setattr__(self, "connections", _freeze(self.connections or ()))

    @property
    def ID(self): return self.id
    @property
    def SFC_JSON(self): return self.path
    @property
    def VNFS(self): return _thaw(self.vnfs)
    @property
    def IP(self): return _thaw(self.ip)
    @property
    def OPS(self): return _thaw(self.ops)
    @property
    def CONNECTIONS(self): return _thaw(self.connections)

    def to_dict(self):
        return {"ID": self.id, "VNFS": _thaw(self.vnfs), "IP": _thaw(self.ip),
                "OPS": _thaw(self.ops), "CONNECTIONS": _thaw(self.connections)}

    @classmethod
    def from_sfc(cls, sfc):
        return cls(id=sfc.ID, path=sfc.SFC_JSON, vnfs=sfc.VNFS,
                   ip=sfc.IP, ops=sfc.OPS, connections=sfc.CONNECTIONS)


@dataclass(frozen=True)
class MininetSwitchSpec:
    id: str
    elem: object = None
    @property
    def ID(self): return self.id
    @property
    def ELEM(self): return self.elem

    def to_dict(self): return self.id


@dataclass(frozen=True)
class MininetControllerSpec:
    id: str
    ip: str
    port: int
    elem: object = None
    @property
    def ID(self): return self.id
    @property
    def IP(self): return self.ip
    @property
    def PORT(self): return self.port
    @property
    def ELEM(self): return self.elem

    def to_dict(self): return {"ID": self.id, "IP": self.ip, "PORT": self.port}


@dataclass(frozen=True)
class MininetOVSSwitchSpec:
    id: str
    controller: str
    elem: object = None
    @property
    def ID(self): return self.id
    @property
    def CONTROLLER(self): return self.controller
    @property
    def ELEM(self): return self.elem

    def to_dict(self): return {"ID": self.id, "CONTROLLER": self.controller}


@dataclass(frozen=True)
class ConnectionSpec:
    inout: str
    outin: str
    inout_iface: str | None = None
    outin_iface: str | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]):
        return cls(inout=data.get("IN/OUT"), outin=data.get("OUT/IN"),
                   inout_iface=data.get("IN/OUTIFACE"), outin_iface=data.get("OUT/INIFACE"))

    def to_dict(self):
        data = {"IN/OUT": self.inout, "OUT/IN": self.outin}
        if self.inout_iface is not None: data["IN/OUTIFACE"] = self.inout_iface
        if self.outin_iface is not None: data["OUT/INIFACE"] = self.outin_iface
        return data

    def __contains__(self, key): return key in self.to_dict()
    def __getitem__(self, key): return self.to_dict()[key]
    def get(self, key, default=None): return self.to_dict().get(key, default)


@dataclass(frozen=True)
class TopologySpec:
    id: str
    vms: tuple[VMSpec, ...] = ()
    vnfs: tuple[VNFSpec, ...] = ()
    sfcs: tuple[SFCSpec, ...] = ()
    containers: tuple[ContainerSpec, ...] = ()
    mininet_hosts: tuple[MininetHostSpec, ...] = ()
    mininet_switches: tuple[MininetSwitchSpec, ...] = ()
    mininet_controllers: tuple[MininetControllerSpec, ...] = ()
    mininet_ovs_switches: tuple[MininetOVSSwitchSpec, ...] = ()
    connections: tuple[ConnectionSpec, ...] = ()

    def __post_init__(self):
        for name in ("vms", "vnfs", "sfcs", "containers", "mininet_hosts",
                     "mininet_switches", "mininet_controllers", "mininet_ovs_switches",
                     "connections"):
            object.__setattr__(self, name, tuple(getattr(self, name) or ()))

    @property
    def ID(self): return self.id

    def to_dict(self):
        return {
            "ID": self.id,
            "VMS": [item.to_dict() for item in self.vms],
            "VNFS": [item.to_dict() for item in self.vnfs],
            "SFCS": [item.to_dict() for item in self.sfcs],
            "CONTAINERS": [item.to_dict() for item in self.containers],
            "MININET": {
                "HOSTS": [item.to_dict() for item in self.mininet_hosts],
                "SWITCHES": [item.to_dict() for item in self.mininet_switches],
                "CONTROLLERS": [item.to_dict() for item in self.mininet_controllers],
                "OVSWITCHES": [item.to_dict() for item in self.mininet_ovs_switches],
            },
            "CONNECTIONS": [item.to_dict() for item in self.connections],
        }
