"""Pure schema and cross-reference validation for loaded topologies."""

from __future__ import annotations

import re
from collections import defaultdict
from os.path import isfile
from typing import Any, Mapping

from niep.domain.spec import (
    ConnectionSpec, ContainerSpec, InterfaceSpec, MininetControllerSpec,
    MininetHostSpec, MininetOVSSwitchSpec, MininetSwitchSpec, SFCSpec,
    TopologySpec, VMSpec, VNFSpec,
)
from niep.domain.topology import DescriptorDocument, TopologyDocument, ValidationIssue, ValidationResult
from .loader import TopologyLoader


MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class TopologyValidator:
    """Validate JSON data without touching Docker, libvirt, Mininet or files.

    ``ValidationResult.issues`` intentionally contains every issue found in a
    pass. The first issue retains the historical numeric parser status.
    """

    def __init__(self, loader: TopologyLoader | None = None):
        self.loader = loader or TopologyLoader()
        self.issues: list[ValidationIssue] = []
        self._document: TopologyDocument | None = None
        self._data: Mapping[str, Any] = {}
        self._source = ""
        self._vms: list[VMSpec] = []
        self._vnfs: list[VNFSpec] = []
        self._sfcs: list[SFCSpec] = []
        self._containers: list[ContainerSpec] = []
        self._hosts: list[MininetHostSpec] = []
        self._switches: list[MininetSwitchSpec] = []
        self._controllers: list[MininetControllerSpec] = []
        self._ovs: list[MininetOVSSwitchSpec] = []
        self._connections: list[ConnectionSpec] = []

    def _add(self, code: int | str, message: str, *, field: str | None = None,
             file: str | None = None, line: int | None = None, value: Any = None):
        self.issues.append(ValidationIssue(code, message, field=field, file=file or self._source,
                                            line=line, value=value))

    @staticmethod
    def check_ip(value: Any, require_prefix: bool = False) -> bool:
        if not isinstance(value, str):
            return False
        address, separator, prefix = value.partition("/")
        octets = address.split(".")
        if len(octets) != 4 or any(not item.isdigit() or int(item) > 255 for item in octets):
            return False
        if require_prefix and not separator:
            return False
        return not separator or (prefix.isdigit() and 0 <= int(prefix) <= 32)

    @staticmethod
    def check_mac(value: Any) -> bool:
        return isinstance(value, str) and bool(MAC_RE.fullmatch(value))

    @staticmethod
    def _is_int(value: Any) -> bool:
        return isinstance(value, int) and not isinstance(value, bool) or (
            isinstance(value, str) and value.isdigit()
        )

    def _descriptor(self, section: str, index: int) -> DescriptorDocument | None:
        if self._document is None:
            return None
        docs = self._document.descriptors.get(section, ())
        return docs[index] if index < len(docs) else None

    def _nested(self, path: str, *, field: str, code: int = -3,
                missing_code: int | None = None) -> DescriptorDocument | None:
        # ``load_descriptor`` does not reset the loader's pending list. Clear
        # it before and transfer newly emitted diagnostics to this pass.
        self.loader._pending_issues = []
        result = self.loader.load_descriptor(path, field=field, code=code,
                                             missing_code=missing_code)
        self.issues.extend(self.loader._pending_issues)
        return result

    def _interfaces(self, raw: Any, *, field: str, code: int, require_id: bool = True,
                    ip_message: str = "Invalid IPv4 address or prefix",
                    file: str | None = None, require_ip_prefix: bool = False) -> tuple[InterfaceSpec, ...]:
        if not isinstance(raw, list):
            self._add(code, "Interfaces must be a list", field=field, file=file, value=raw)
            return ()
        result: list[InterfaceSpec] = []
        seen_ids: set[str] = set()
        seen_macs: set[str] = set()
        for index, iface in enumerate(raw):
            current = f"{field}[{index}]"
            if not isinstance(iface, dict):
                self._add(code, "Interface must be a JSON object", field=current, file=file, value=iface)
                continue
            if require_id and "ID" not in iface:
                self._add(code, "Missing required interface key", field=current + ".ID", file=file)
            iface_id = iface.get("ID")
            if iface_id is not None and (not isinstance(iface_id, str) or not iface_id):
                self._add(code, "Interface ID must be a non-empty string", field=current + ".ID", file=file, value=iface_id)
            if iface_id in seen_ids and iface_id is not None:
                self._add(code, "Duplicate interface ID", field=current + ".ID", file=file, value=iface_id)
            if "MAC" not in iface:
                self._add(code, "Missing required interface key", field=current + ".MAC", file=file)
            mac = iface.get("MAC")
            if not self.check_mac(mac):
                self._add(code, "Invalid MAC address", field=current + ".MAC", file=file, value=mac)
            elif mac.lower() in seen_macs:
                self._add(-11, "Duplicate interface MAC", field=current + ".MAC", file=file, value=mac)
            ip = iface.get("IP")
            if ip is not None and not self.check_ip(ip, require_ip_prefix):
                self._add(code, ip_message, field=current + ".IP", file=file, value=ip)
            link_mac = iface.get("LINK_MAC")
            if link_mac is not None and not self.check_mac(link_mac):
                self._add(code, "Invalid LINK_MAC address", field=current + ".LINK_MAC", file=file, value=link_mac)
            if isinstance(iface_id, str): seen_ids.add(iface_id)
            if isinstance(mac, str) and self.check_mac(mac): seen_macs.add(mac.lower())
            result.append(InterfaceSpec.from_dict(iface))
        return tuple(result)

    def _vm(self, doc: DescriptorDocument, field: str, *, forced_id: str | None = None) -> VMSpec | None:
        raw = doc.data
        valid = True
        vm_id = forced_id if forced_id is not None else raw.get("ID")
        if not isinstance(vm_id, str) or not vm_id:
            self._add(-3, "VM field ID must be a non-empty string", field=field + ".ID", file=doc.path, value=vm_id); valid = False
        memory = raw.get("MEMORY")
        if not isinstance(memory, int) or isinstance(memory, bool) or memory <= 0:
            self._add(-3, "VM field MEMORY must be a positive integer", field=field + ".MEMORY", file=doc.path, value=memory); valid = False
        vcpu = raw.get("VCPU")
        if not isinstance(vcpu, int) or isinstance(vcpu, bool) or vcpu <= 0:
            self._add(-3, "VM field VCPU must be a positive integer", field=field + ".VCPU", file=doc.path, value=vcpu); valid = False
        disk = raw.get("DISK")
        if disk not in {"tinycore12", "click-on-osv"}:
            self._add(-3, "VM field DISK is invalid", field=field + ".DISK", file=doc.path, value=disk); valid = False
        management = raw.get("MANAGEMENT_MAC")
        if not self.check_mac(management):
            self._add(-3, "VM field MANAGEMENT_MAC is invalid", field=field + ".MANAGEMENT_MAC", file=doc.path, value=management); valid = False
        interfaces = self._interfaces(raw.get("INTERFACES"), field=field + ".INTERFACES", code=-3, require_id=True, file=doc.path)
        if not valid:
            return None
        return VMSpec(vm_id, doc.path, memory, vcpu, disk, management, interfaces)

    def _container(self, doc: DescriptorDocument, field: str) -> ContainerSpec | None:
        raw = doc.data
        valid = True
        ident = raw.get("ID")
        if not isinstance(ident, str) or not ident:
            self._add(-3, "Container field ID must be a non-empty string", field=field + ".ID", file=doc.path, value=ident); valid = False
        elif not ID_RE.fullmatch(ident):
            self._add(-3, "Container field ID contains characters unsupported by Docker", field=field + ".ID", file=doc.path, value=ident); valid = False
        image = raw.get("IMAGE")
        if not isinstance(image, str) or not image:
            self._add(-3, "Container field IMAGE must be a non-empty string", field=field + ".IMAGE", file=doc.path, value=image); valid = False
        command = raw.get("COMMAND", ["sleep", "infinity"])
        if not isinstance(command, (str, list)) or (isinstance(command, list) and not all(isinstance(x, str) for x in command)):
            self._add(-3, "Container field COMMAND must be a string or list", field=field + ".COMMAND", file=doc.path, value=command); valid = False
        entrypoint = raw.get("ENTRYPOINT")
        if entrypoint is not None and (not isinstance(entrypoint, (str, list)) or (isinstance(entrypoint, list) and not all(isinstance(x, str) for x in entrypoint))):
            self._add(-3, "Container field ENTRYPOINT must be null, a string or list", field=field + ".ENTRYPOINT", file=doc.path, value=entrypoint); valid = False
        privileged = raw.get("PRIVILEGED", True)
        if not isinstance(privileged, bool):
            self._add(-3, "Container field PRIVILEGED must be boolean", field=field + ".PRIVILEGED", file=doc.path, value=privileged); valid = False
        sysctls = raw.get("SYSCTLS", {})
        if not isinstance(sysctls, dict):
            self._add(-3, "Container SYSCTLS must be a JSON object", field=field + ".SYSCTLS", file=doc.path, value=sysctls); valid = False
        else:
            for key, value in sysctls.items():
                if not isinstance(key, str) or not key or not isinstance(value, (str, int, bool)):
                    self._add(-3, "Container SYSCTLS keys and values are invalid", field=field + ".SYSCTLS." + str(key), file=doc.path, value=value); valid = False
        interfaces = self._interfaces(raw.get("INTERFACES", []), field=field + ".INTERFACES", code=-3,
                                      require_id=True, ip_message="IP is not a valid IP address with prefix", file=doc.path,
                                      require_ip_prefix=True)
        if not valid:
            return None
        return ContainerSpec(ident, doc.path, image, command, entrypoint, privileged, sysctls, interfaces)

    def _vnf(self, doc: DescriptorDocument, field: str, *, forced_id: str | None = None) -> VNFSpec | None:
        raw = doc.data
        ident = forced_id if forced_id is not None else raw.get("ID")
        valid = True
        if not isinstance(ident, str) or not ident:
            self._add(-3, "VNF field ID must be a non-empty string", field=field + ".ID", file=doc.path, value=ident); valid = False
        vm_ref = raw.get("VM")
        if not isinstance(vm_ref, str):
            self._add(-3, "VNF field VM must be a descriptor path", field=field + ".VM", file=doc.path, value=vm_ref); return None
        vm_path = self.loader.resolve_path(vm_ref, doc.path)
        vm_doc = self._nested(vm_path, field=field + ".VM", code=-3)
        vm = self._vm(vm_doc, field + ".VM", forced_id=ident) if vm_doc is not None else None
        if vm is None: valid = False
        if not valid: return None
        return VNFSpec(ident, doc.path, vm_path, vm)

    def _sfc(self, doc: DescriptorDocument, field: str) -> tuple[SFCSpec | None, list[VNFSpec]]:
        raw = doc.data
        valid = True
        ident = raw.get("ID")
        if not isinstance(ident, str) or not ident:
            self._add(-5, "SFC field ID must be a non-empty string", field=field + ".ID", file=doc.path, value=ident); valid = False
        vnfs = raw.get("VNFS")
        ip = raw.get("IP")
        ops = raw.get("OPS")
        connections = raw.get("CONNECTIONS")
        if not isinstance(vnfs, list) or not vnfs:
            self._add(-5, "SFC VNFS must be a non-empty list", field=field + ".VNFS", file=doc.path, value=vnfs); valid = False
        if not isinstance(ip, dict) or not ip:
            self._add(-5, "SFC IP must be a non-empty object", field=field + ".IP", file=doc.path, value=ip); valid = False
        if not isinstance(ops, list) or not ops:
            self._add(-5, "SFC OPS must be a non-empty list", field=field + ".OPS", file=doc.path, value=ops); valid = False
        if not isinstance(connections, list) or not connections:
            self._add(-5, "SFC CONNECTIONS must be a non-empty list", field=field + ".CONNECTIONS", file=doc.path, value=connections); valid = False
        nested_vnfs: list[VNFSpec] = []
        vnf_ids: set[str] = set()
        normalized_vnfs: list[dict[str, Any]] = []
        for index, reference in enumerate(vnfs if isinstance(vnfs, list) else []):
            item_field = f"{field}.VNFS[{index}]"
            if not isinstance(reference, dict) or not isinstance(reference.get("ID"), str) or not isinstance(reference.get("PATH"), str):
                self._add(-5, "SFC VNF requires ID and PATH", field=item_field, file=doc.path, value=reference); valid = False; continue
            vnf_id = reference["ID"]
            if vnf_id in vnf_ids:
                self._add(-5, "Duplicate VNF ID inside SFC", field=item_field + ".ID", file=doc.path, value=vnf_id); valid = False
            vnf_ids.add(vnf_id)
            vnf_path = self.loader.resolve_path(reference["PATH"], doc.path)
            vnf_doc = self._nested(vnf_path, field=item_field + ".PATH", code=-3,
                                   missing_code=-2)
            if vnf_doc is not None and vnf_doc.data.get("ID") != vnf_id:
                self._add(
                    -5,
                    "SFC VNF reference ID does not match descriptor ID",
                    field=item_field + ".ID",
                    file=vnf_doc.path,
                    value={"reference": vnf_id, "descriptor": vnf_doc.data.get("ID")},
                )
                valid = False
            vnf = self._vnf(vnf_doc, item_field, forced_id=vnf_id) if vnf_doc is not None else None
            if vnf is None: valid = False
            else: nested_vnfs.append(vnf)
            normalized = dict(reference); normalized["PATH"] = vnf_path; normalized_vnfs.append(normalized)
        if isinstance(ip, dict):
            if not isinstance(ip.get("ID"), str) or not isinstance(ip.get("LINK"), str):
                self._add(-5, "SFC IP requires ID and LINK", field=field + ".IP", file=doc.path, value=ip); valid = False
        op_ids: set[str] = set()
        for index, op in enumerate(ops if isinstance(ops, list) else []):
            item_field = f"{field}.OPS[{index}]"
            if not isinstance(op, dict) or not isinstance(op.get("ID"), str) or not isinstance(op.get("LINK"), str):
                self._add(-5, "SFC operation requires ID and LINK", field=item_field, file=doc.path, value=op); valid = False; continue
            if op["ID"] in op_ids: self._add(-5, "Duplicate SFC operation ID", field=item_field + ".ID", file=doc.path, value=op["ID"]); valid = False
            op_ids.add(op["ID"])
        # The graph rules mirror the legacy SFC validator while accumulating
        # diagnostics instead of returning after the first mismatch.
        if isinstance(connections, list) and isinstance(ip, dict):
            ill = [x.get("ILL") for x in connections if isinstance(x, dict)]
            oll = [x.get("OLL") for x in connections if isinstance(x, dict)]
            if oll.count(ip.get("ID")) != 1 or ip.get("ID") in ill:
                self._add(-5, "SFC incoming point graph is invalid", field=field + ".CONNECTIONS", file=doc.path); valid = False
            for op_id in op_ids:
                if op_id not in ill or op_id in oll:
                    self._add(-5, "SFC operation graph is invalid", field=field + ".CONNECTIONS", file=doc.path, value=op_id); valid = False
            for vnf_id in vnf_ids:
                if vnf_id not in ill or vnf_id not in oll:
                    self._add(-5, "SFC VNF graph is invalid", field=field + ".CONNECTIONS", file=doc.path, value=vnf_id); valid = False
            for connection in connections:
                if isinstance(connection, dict) and connection.get("ILL") == connection.get("OLL"):
                    self._add(-5, "SFC connection cannot link an endpoint to itself", field=field + ".CONNECTIONS", file=doc.path, value=connection); valid = False
        if not valid:
            return None, nested_vnfs
        return SFCSpec(ident, doc.path, tuple(normalized_vnfs), ip, tuple(ops), tuple(connections)), nested_vnfs

    def _mininet(self, raw: Any):
        if not isinstance(raw, dict):
            self._add(-6, "Expected a JSON object", field="MININET", value=raw); return
        for key in ("HOSTS", "SWITCHES", "CONTROLLERS", "OVSWITCHES"):
            if key not in raw: self._add(-6, "Missing required Mininet key", field="MININET." + key); continue
            if not isinstance(raw.get(key), list): self._add(-6, "Expected a list", field="MININET." + key, value=raw.get(key))
        ids = {"UNICTRL"}
        for index, host in enumerate(raw.get("HOSTS", []) if isinstance(raw.get("HOSTS"), list) else []):
            field = f"MININET.HOSTS[{index}]"
            if not isinstance(host, dict): self._add(-7, "Host must be a JSON object", field=field, value=host); continue
            ident = host.get("ID")
            if not isinstance(ident, str) or not ident: self._add(-7, "Host ID must be a non-empty string", field=field + ".ID", value=ident); continue
            if ident in ids: self._add(-7, "Duplicate topology node ID", field=field + ".ID", value=ident)
            interfaces = self._interfaces(host.get("INTERFACES"), field=field + ".INTERFACES", code=-7, require_id=False)
            self._hosts.append(MininetHostSpec(ident, interfaces)); ids.add(ident)
        for index, ident in enumerate(raw.get("SWITCHES", []) if isinstance(raw.get("SWITCHES"), list) else []):
            field = f"MININET.SWITCHES[{index}]"
            if not isinstance(ident, str) or not ident: self._add(-8, "Switch ID must be a non-empty string", field=field, value=ident); continue
            if ident in ids: self._add(-8, "Duplicate topology node ID", field=field, value=ident)
            self._switches.append(MininetSwitchSpec(ident)); ids.add(ident)
        controller_ids: set[str] = set()
        for index, controller in enumerate(raw.get("CONTROLLERS", []) if isinstance(raw.get("CONTROLLERS"), list) else []):
            field = f"MININET.CONTROLLERS[{index}]"
            if not isinstance(controller, dict): self._add(-9, "Controller must be a JSON object", field=field, value=controller); continue
            ident, ip, port = controller.get("ID"), controller.get("IP"), controller.get("PORT")
            if not isinstance(ident, str) or not ident: self._add(-9, "Controller ID must be a non-empty string", field=field + ".ID", value=ident)
            if ident in ids or ident in controller_ids: self._add(-9, "Duplicate topology node ID", field=field + ".ID", value=ident)
            if not isinstance(ip, str) or not self.check_ip(ip + "/32"): self._add(-9, "Invalid controller IPv4 address", field=field + ".IP", value=ip)
            if not self._is_int(port) or not 1 <= int(port) <= 65535: self._add(-9, "Controller port must be between 1 and 65535", field=field + ".PORT", value=port)
            if isinstance(ident, str): controller_ids.add(ident); self._controllers.append(MininetControllerSpec(ident, ip, int(port) if self._is_int(port) else 0)); ids.add(ident)
        for index, ovs in enumerate(raw.get("OVSWITCHES", []) if isinstance(raw.get("OVSWITCHES"), list) else []):
            field = f"MININET.OVSWITCHES[{index}]"
            if not isinstance(ovs, dict): self._add(-10, "OVS switch must be a JSON object", field=field, value=ovs); continue
            ident, controller = ovs.get("ID"), ovs.get("CONTROLLER")
            if not isinstance(ident, str) or not ident: self._add(-10, "OVS switch ID must be a non-empty string", field=field + ".ID", value=ident); continue
            if ident in ids or ident in controller_ids: self._add(-10, "Duplicate topology node ID", field=field + ".ID", value=ident)
            if controller not in controller_ids: self._add(-10, "OVS switch references an unknown controller", field=field + ".CONTROLLER", value=controller)
            self._ovs.append(MininetOVSSwitchSpec(ident, controller)); ids.add(ident)

    def _identity(self):
        owners: dict[str, str] = {}
        resources = [(x.id, "VM") for x in self._vms] + [(x.id, "VNF") for x in self._vnfs] + [(x.id, "container") for x in self._containers]
        resources += [(x.id, "SFC") for x in self._sfcs]
        resources += [(x.id, "Mininet host") for x in self._hosts] + [(x.id, "Mininet switch") for x in self._switches]
        resources += [(x.id, "Mininet controller") for x in self._controllers] + [(x.id, "Mininet OVS switch") for x in self._ovs]
        for ident, kind in resources:
            if ident in owners: self._add(-11, f"Duplicate resource ID shared by {owners[ident]} and {kind}", field="ID", value=ident)
            else: owners[ident] = kind
        interface_ids: dict[str, str] = {}
        interface_macs: dict[str, str] = {}
        endpoint_resources = [(x.id, x.interfaces) for x in self._vms] + [(x.id, x.interfaces) for x in self._containers]
        endpoint_resources += [(x.id, x.vm.interfaces) for x in self._vnfs]
        endpoint_resources += [(x.id, x.interfaces) for x in self._hosts]
        management_macs: dict[str, str] = {}
        for owner, management_mac in (
            [(x.id, x.management_mac) for x in self._vms]
            + [(x.id, x.vm.management_mac) for x in self._vnfs]
        ):
            normalized = management_mac.lower()
            if normalized in management_macs:
                self._add(-11, "Duplicate management MAC", field="MANAGEMENT_MAC", value=management_mac)
            else:
                management_macs[normalized] = owner
            if normalized in interface_macs:
                self._add(-11, "Duplicate external interface MAC", field="MANAGEMENT_MAC", value=management_mac)
            else:
                interface_macs[normalized] = owner
        for owner, interfaces in endpoint_resources:
            for iface in interfaces:
                if iface.id and iface.id in interface_ids: self._add(-11, "Duplicate external interface ID", field="INTERFACES.ID", value=iface.id)
                elif iface.id: interface_ids[iface.id] = owner
                if iface.mac and iface.mac.lower() in interface_macs: self._add(-11, "Duplicate external interface MAC", field="INTERFACES.MAC", value=iface.mac)
                elif iface.mac: interface_macs[iface.mac.lower()] = owner

    def _validate_connections(self, raw: Any):
        if not isinstance(raw, list): self._add(-11, "Expected a list", field="CONNECTIONS", value=raw); return
        endpoints: dict[str, Any] = {}
        for resource in self._vms + self._containers: endpoints[resource.id] = resource
        for resource in self._vnfs: endpoints[resource.id] = resource.vm
        for host in self._hosts: endpoints[host.id] = host
        network = {x.id for x in self._switches + self._ovs}
        used: set[tuple[str, str]] = set()
        for index, connection in enumerate(raw):
            field = f"CONNECTIONS[{index}]"
            if not isinstance(connection, dict): self._add(-11, "Connection must be a JSON object", field=field, value=connection); continue
            for endpoint_key, iface_key, code in (("IN/OUT", "IN/OUTIFACE", -12), ("OUT/IN", "OUT/INIFACE", -13)):
                endpoint = connection.get(endpoint_key)
                if not isinstance(endpoint, str) or not endpoint: self._add(code, "Connection endpoint must be a non-empty string", field=field + "." + endpoint_key, value=endpoint); continue
                if endpoint not in endpoints and endpoint not in network: self._add(code, "Connection references an unknown endpoint", field=field + "." + endpoint_key, value=endpoint); continue
                if endpoint in endpoints:
                    mac = connection.get(iface_key)
                    if iface_key not in connection: self._add(code, "External endpoint requires an interface MAC", field=field + "." + iface_key); continue
                    available = [iface.mac for iface in endpoints[endpoint].interfaces]
                    if mac not in available: self._add(code, f"Interface MAC does not belong to endpoint {endpoint}; available={available!r}", field=field + "." + iface_key, value=mac); continue
                    marker = (endpoint, str(mac).lower())
                    if marker in used: self._add(-11, "External interface is used by more than one connection", field=field + "." + iface_key, value=mac)
                    used.add(marker)
            if connection.get("OUT/IN") == connection.get("IN/OUT"): self._add(-14, "A connection cannot link an endpoint to itself", field=field, value=connection.get("IN/OUT"))
            self._connections.append(ConnectionSpec.from_dict(connection))

    def validate(self, document: TopologyDocument | Mapping[str, Any]) -> ValidationResult:
        self.__init__(self.loader)
        if isinstance(document, TopologyDocument):
            self._document, self._data, self._source = document, document.data, document.path
            # Loader issues are included before schema issues so legacy status
            # selection remains deterministic.
            if self.loader.last_result is not None and self.loader.last_result.issues:
                self.issues.extend(self.loader.last_result.issues)
        else:
            self._source = ""
            self._data = document
            self._document = TopologyDocument("", document, {})
        required = ("ID", "VMS", "VNFS", "SFCS", "MININET", "CONNECTIONS")
        for key in required:
            if key not in self._data: self._add(-1, "Missing required key", field=key)
        root_id = self._data.get("ID")
        if not isinstance(root_id, str): self._add(-2, "Expected a string", field="ID", value=root_id)
        for key in ("VMS", "VNFS", "SFCS"):
            if key in self._data and not isinstance(self._data[key], list): self._add(-2, "Expected a list", field=key, value=self._data[key])
        if "CONTAINERS" in self._data and not isinstance(self._data["CONTAINERS"], list): self._add(-2, "Expected a list", field="CONTAINERS", value=self._data["CONTAINERS"])
        if not isinstance(self._data.get("MININET"), dict): self._add(-6, "Expected a JSON object", field="MININET", value=self._data.get("MININET"))
        if not isinstance(self._data.get("CONNECTIONS"), list): self._add(-11, "Expected a list", field="CONNECTIONS", value=self._data.get("CONNECTIONS"))
        for index, doc in enumerate(self._document.descriptors.get("VMS", ())):
            if doc is None:
                continue
            vm = self._vm(doc, f"VMS[{index}]")
            if vm is not None: self._vms.append(vm)
        for index, doc in enumerate(self._document.descriptors.get("CONTAINERS", ())):
            if doc is None:
                continue
            item = self._container(doc, f"CONTAINERS[{index}]")
            if item is not None: self._containers.append(item)
        for index, doc in enumerate(self._document.descriptors.get("VNFS", ())):
            if doc is None:
                continue
            item = self._vnf(doc, f"VNFS[{index}]")
            if item is not None: self._vnfs.append(item)
        for index, doc in enumerate(self._document.descriptors.get("SFCS", ())):
            if doc is None:
                continue
            item, nested = self._sfc(doc, f"SFCS[{index}]")
            if item is not None: self._sfcs.append(item)
            self._vnfs.extend(nested)
        self._mininet(self._data.get("MININET"))
        self._identity()
        self._validate_connections(self._data.get("CONNECTIONS"))
        spec = None
        if isinstance(root_id, str):
            spec = TopologySpec(root_id, tuple(self._vms), tuple(self._vnfs), tuple(self._sfcs), tuple(self._containers), tuple(self._hosts), tuple(self._switches), tuple(self._controllers), tuple(self._ovs), tuple(self._connections))
        return ValidationResult(value=spec, issues=tuple(self.issues))

    check = validate

    def validate_spec(self, document: TopologyDocument | Mapping[str, Any]):
        result = self.validate(document)
        return result.value if result.ok else None
