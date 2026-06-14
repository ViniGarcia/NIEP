from dataclasses import dataclass, field


@dataclass
class InterfaceSpec:
    mac: str
    ip: str = None
    id: str = None
    link_mac: str = None
    elem: object = None

    @classmethod
    def from_dict(cls, data):
        return cls(
            id=data.get("ID"),
            mac=data.get("MAC"),
            ip=data.get("IP"),
            link_mac=data.get("LINK_MAC"),
            elem=data.get("ELEM"),
        )

    def to_dict(self):
        data = {
            "MAC": self.mac,
            "IP": self.ip,
        }
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

    def __setitem__(self, key, value):
        if key == "ID":
            self.id = value
        elif key == "MAC":
            self.mac = value
        elif key == "IP":
            self.ip = value
        elif key == "LINK_MAC":
            self.link_mac = value
        elif key == "ELEM":
            self.elem = value
        else:
            raise KeyError(key)

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


@dataclass
class MininetHostSpec:
    id: str
    interfaces: list
    elem: object = None

    @property
    def ID(self):
        return self.id

    @property
    def INTERFACES(self):
        return self.interfaces

    @property
    def ELEM(self):
        return self.elem

    @ELEM.setter
    def ELEM(self, value):
        self.elem = value


@dataclass
class VMSpec:
    id: str
    path: str
    memory: int
    vcpu: int
    disk: str
    management_mac: str
    interfaces: list = field(default_factory=list)

    @classmethod
    def from_vm(cls, vm):
        return cls(
            id=vm.ID,
            path=vm.VM_JSON,
            memory=vm.MEMORY,
            vcpu=vm.VCPU,
            disk=vm.DISK,
            management_mac=vm.MANAGEMENT_MAC,
            interfaces=[InterfaceSpec.from_dict(iface) for iface in vm.INTERFACES],
        )


@dataclass
class VNFSpec:
    id: str
    path: str
    vm_path: str
    vm: VMSpec

    @classmethod
    def from_vnf(cls, vnf):
        return cls(
            id=vnf.ID,
            path=vnf.VNF_JSON,
            vm_path=vnf.VM.VM_JSON,
            vm=VMSpec.from_vm(vnf.VM),
        )


@dataclass
class SFCSpec:
    id: str
    path: str
    vnfs: list = field(default_factory=list)
    ip: dict = field(default_factory=dict)
    ops: list = field(default_factory=list)
    connections: list = field(default_factory=list)

    @classmethod
    def from_sfc(cls, sfc):
        return cls(
            id=sfc.ID,
            path=sfc.SFC_JSON,
            vnfs=sfc.VNFS,
            ip=sfc.IP,
            ops=sfc.OPS,
            connections=sfc.CONNECTIONS,
        )


@dataclass
class MininetSwitchSpec:
    id: str
    elem: object = None

    @property
    def ID(self):
        return self.id

    @property
    def ELEM(self):
        return self.elem

    @ELEM.setter
    def ELEM(self, value):
        self.elem = value


@dataclass
class MininetControllerSpec:
    id: str
    ip: str
    port: int
    elem: object = None

    @property
    def ID(self):
        return self.id

    @property
    def IP(self):
        return self.ip

    @property
    def PORT(self):
        return self.port

    @property
    def ELEM(self):
        return self.elem

    @ELEM.setter
    def ELEM(self, value):
        self.elem = value


@dataclass
class MininetOVSSwitchSpec:
    id: str
    controller: str
    elem: object = None

    @property
    def ID(self):
        return self.id

    @property
    def CONTROLLER(self):
        return self.controller

    @property
    def ELEM(self):
        return self.elem

    @ELEM.setter
    def ELEM(self, value):
        self.elem = value


@dataclass
class ConnectionSpec:
    inout: str
    outin: str
    inout_iface: str = None
    outin_iface: str = None

    @classmethod
    def from_dict(cls, data):
        return cls(
            inout=data.get("IN/OUT"),
            outin=data.get("OUT/IN"),
            inout_iface=data.get("IN/OUTIFACE"),
            outin_iface=data.get("OUT/INIFACE"),
        )

    def to_dict(self):
        data = {
            "IN/OUT": self.inout,
            "OUT/IN": self.outin,
        }
        if self.inout_iface is not None:
            data["IN/OUTIFACE"] = self.inout_iface
        if self.outin_iface is not None:
            data["OUT/INIFACE"] = self.outin_iface
        return data

    def __contains__(self, key):
        return key in self.to_dict()

    def __getitem__(self, key):
        return self.to_dict()[key]

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


@dataclass
class TopologySpec:
    id: str
    vms: list = field(default_factory=list)
    vnfs: list = field(default_factory=list)
    sfcs: list = field(default_factory=list)
    mininet_hosts: list = field(default_factory=list)
    mininet_switches: list = field(default_factory=list)
    mininet_controllers: list = field(default_factory=list)
    mininet_ovs_switches: list = field(default_factory=list)
    connections: list = field(default_factory=list)

    @property
    def ID(self):
        return self.id
