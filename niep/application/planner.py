"""Pure planning of the Mininet part of a topology.

The planner deliberately knows nothing about Mininet (or any other optional
runtime).  It turns the immutable topology descriptors and the already known
host interface mapping into a deterministic, inspectable value object.  The
Mininet adapter is the only layer which turns this value object into runtime
resources.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from ipaddress import ip_interface
import re
from typing import Any, Iterable, Mapping

from niep.domain.spec import TopologySpec
from niep.domain.topology import ValidationIssue, ValidationResult


_MAC_RE = re.compile(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}")


class EndpointKind(str, Enum):
    """Kinds of endpoint that may occur at a connection side."""

    HOST = "host"
    SWITCH = "switch"
    OVS_SWITCH = "ovs-switch"
    EXTERNAL = "external"
    CONTROLLER = "controller"

    @property
    def is_network_node(self) -> bool:
        return self in (EndpointKind.SWITCH, EndpointKind.OVS_SWITCH)


# Names used by callers that prefer the shorter terminology.
EndpointType = EndpointKind


@dataclass(frozen=True, init=False)
class EndpointId:
    """Stable typed identifier for one endpoint.

    ``EndpointId("h1", EndpointKind.HOST)`` is the canonical form.  ``id``,
    ``name`` and ``value`` are intentionally available as aliases because
    older callers use all three names for topology IDs.
    """

    id: str
    kind: EndpointKind

    def __init__(
        self,
        id: str | EndpointKind,
        kind: EndpointKind | str,
        *,
        name: str | None = None,
        value: str | None = None,
    ) -> None:
        # Accept the occasionally-used (kind, id) positional spelling too.
        if isinstance(id, (EndpointKind,)) and isinstance(kind, str):
            id, kind = kind, id
        ident = name if name is not None else value if value is not None else id
        if not isinstance(ident, str) or not ident:
            raise ValueError("endpoint ID must be a non-empty string")
        object.__setattr__(self, "id", ident)
        object.__setattr__(self, "kind", EndpointKind(kind))

    @property
    def name(self) -> str:
        return self.id

    @property
    def value(self) -> str:
        return self.id

    @property
    def is_external(self) -> bool:
        return self.kind is EndpointKind.EXTERNAL

    def __str__(self) -> str:
        return self.id

    def to_dict(self) -> dict[str, str]:
        return {"id": self.id, "kind": self.kind.value}


class LinkStrategy(str, Enum):
    HOST_HOST = "host-host"
    HOST_SWITCH = "host-switch"
    SWITCH_SWITCH = "switch-switch"
    HOST_EXTERNAL = "host-endpoint-external"
    SWITCH_EXTERNAL = "switch-endpoint-external"


# A readable alias for consumers that call this a link kind.
LinkKind = LinkStrategy


@dataclass(frozen=True)
class InterfaceAssignment:
    """A connection side resolved to one descriptor interface."""

    endpoint: EndpointId
    mac: str
    ip: str | None = None
    interface_id: str | None = None
    bridge: str | None = None
    connection_index: int | None = None
    side: str | None = None
    connected: bool = True

    @property
    def id(self) -> str | None:
        return self.interface_id

    @property
    def name(self) -> str | None:
        return self.interface_id

    @property
    def interface(self) -> str | None:
        return self.bridge or self.interface_id

    @property
    def effective_interface(self) -> str | None:
        return self.interface

    @property
    def endpoint_id(self) -> str:
        return self.endpoint.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint": self.endpoint.to_dict(),
            "mac": self.mac,
            "ip": self.ip,
            "interface_id": self.interface_id,
            "bridge": self.bridge,
            "connection_index": self.connection_index,
            "side": self.side,
            "connected": self.connected,
        }


@dataclass(frozen=True)
class NodePlan:
    """One Mininet node to materialize, in descriptor order."""

    endpoint: EndpointId
    interfaces: tuple[InterfaceAssignment, ...] = ()
    controller_id: str | None = None

    @property
    def id(self) -> str:
        return self.endpoint.id

    @property
    def name(self) -> str:
        return self.endpoint.id

    @property
    def kind(self) -> EndpointKind:
        return self.endpoint.kind

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "interfaces": [item.to_dict() for item in self.interfaces],
            "controller_id": self.controller_id,
        }


@dataclass(frozen=True)
class ControllerPlan:
    id: str
    ip: str
    port: int
    local: bool = False

    @property
    def endpoint(self) -> EndpointId:
        return EndpointId(self.id, EndpointKind.CONTROLLER)

    def to_dict(self) -> dict[str, Any]:
        return {"id": self.id, "ip": self.ip, "port": self.port, "local": self.local}


@dataclass(frozen=True)
class LinkPlan:
    """A validated connection and its resolved endpoint interfaces."""

    source: EndpointId
    target: EndpointId
    strategy: LinkStrategy
    source_interface: InterfaceAssignment | None = None
    target_interface: InterfaceAssignment | None = None
    connection_index: int = 0

    @property
    def left(self) -> EndpointId:
        return self.source

    @property
    def right(self) -> EndpointId:
        return self.target

    @property
    def kind(self) -> LinkStrategy:
        return self.strategy

    @property
    def source_mac(self) -> str | None:
        return self.source_interface.mac if self.source_interface else None

    @property
    def target_mac(self) -> str | None:
        return self.target_interface.mac if self.target_interface else None

    @property
    def inout(self) -> str:
        return self.source.id

    @property
    def outin(self) -> str:
        return self.target.id

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "strategy": self.strategy.value,
            "source_interface": self.source_interface.to_dict() if self.source_interface else None,
            "target_interface": self.target_interface.to_dict() if self.target_interface else None,
            "connection_index": self.connection_index,
        }


@dataclass(frozen=True)
class PlanningDiagnostic:
    """Structured planning error, with the historical integer status."""

    code: int | str
    message: str
    field: str | None = None
    value: Any = None
    connection_index: int | None = None
    severity: str = "error"

    @property
    def status(self) -> int | str:
        return self.code

    @property
    def path(self) -> str | None:
        return self.field

    @property
    def legacy_code(self) -> int | str:
        return self.code

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "value": self.value,
            "connection_index": self.connection_index,
            "severity": self.severity,
        }

    def __str__(self) -> str:
        detail = self.message
        if self.field:
            detail += "; field=" + self.field
        if self.value is not None:
            detail += "; value=" + repr(self.value)
        return detail


@dataclass(frozen=True)
class TopologyPlan:
    """Complete deterministic plan consumed by :class:`MininetTopologyAdapter`."""

    nodes: tuple[NodePlan, ...] = ()
    links: tuple[LinkPlan, ...] = ()
    controllers: tuple[ControllerPlan, ...] = ()
    assignments: tuple[InterfaceAssignment, ...] = ()
    switch_controller_id: str | None = None
    diagnostics: tuple[PlanningDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "nodes", tuple(self.nodes or ()))
        object.__setattr__(self, "links", tuple(self.links or ()))
        object.__setattr__(self, "controllers", tuple(self.controllers or ()))
        object.__setattr__(self, "assignments", tuple(self.assignments or ()))
        object.__setattr__(self, "diagnostics", tuple(self.diagnostics or ()))

    @property
    def issues(self) -> tuple[PlanningDiagnostic, ...]:
        return self.diagnostics

    @property
    def errors(self) -> tuple[PlanningDiagnostic, ...]:
        return self.diagnostics

    @property
    def ok(self) -> bool:
        return not self.diagnostics

    @property
    def valid(self) -> bool:
        return self.ok

    @property
    def status(self) -> int | str:
        return self.diagnostics[0].code if self.diagnostics else 0

    @property
    def code(self) -> int | str:
        return self.status

    @property
    def value(self) -> "TopologyPlan":
        return self

    def detail(self) -> str:
        return " | ".join(str(item) for item in self.diagnostics)

    def __bool__(self) -> bool:
        return self.ok

    @property
    def node_plans(self) -> tuple[NodePlan, ...]:
        return self.nodes

    @property
    def link_plans(self) -> tuple[LinkPlan, ...]:
        return self.links

    @property
    def controller_plans(self) -> tuple[ControllerPlan, ...]:
        return self.controllers

    @property
    def interface_assignments(self) -> tuple[InterfaceAssignment, ...]:
        return self.assignments

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [item.to_dict() for item in self.nodes],
            "links": [item.to_dict() for item in self.links],
            "controllers": [item.to_dict() for item in self.controllers],
            "assignments": [item.to_dict() for item in self.assignments],
            "switch_controller_id": self.switch_controller_id,
            "diagnostics": [item.to_dict() for item in self.diagnostics],
        }


class TopologyPlanningError(ValueError):
    """Raised when a connection cannot be represented safely in Mininet."""

    def __init__(self, diagnostics: Iterable[PlanningDiagnostic]):
        self.diagnostics = tuple(diagnostics)
        self.issues = self.diagnostics
        self.status = self.diagnostics[0].code if self.diagnostics else -3
        self.code = self.status
        super().__init__(" | ".join(str(item) for item in self.diagnostics))

    @property
    def detail(self) -> str:
        return str(self)


# Short name used by application callers that do not need to distinguish the
# planning phase from other topology validation errors.
PlanningError = TopologyPlanningError


@dataclass(frozen=True)
class _EndpointData:
    endpoint: EndpointId
    interfaces: tuple[Any, ...] = ()


def _attr(value: Any, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(value, Mapping) and name in value:
            return value[name]
        if hasattr(value, name):
            return getattr(value, name)
    return default


def _items(value: Any) -> tuple[Any, ...]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes, Mapping)):
        return (value,)
    try:
        return tuple(value)
    except TypeError:
        return (value,)


def _connection_value(connection: Any, name: str, default: Any = None) -> Any:
    aliases = {
        "inout": ("inout", "IN/OUT"),
        "outin": ("outin", "OUT/IN"),
        "inout_iface": ("inout_iface", "IN/OUTIFACE"),
        "outin_iface": ("outin_iface", "OUT/INIFACE"),
    }
    return _attr(connection, *aliases[name], default=default)


def _interface_value(interface: Any, name: str, default: Any = None) -> Any:
    aliases = {
        "mac": ("mac", "MAC"),
        "ip": ("ip", "IP"),
        "id": ("id", "ID"),
    }
    return _attr(interface, *aliases[name], default=default)


class TopologyPlanner:
    """Build a plan without importing or touching an infrastructure runtime."""

    def __init__(
        self,
        spec: Any = None,
        *,
        interface_mapping: Mapping[str, Any] | None = None,
        external_endpoints: Mapping[str, Any] | None = None,
        local_pox_enabled: bool = True,
    ) -> None:
        self.spec = spec
        self.interface_mapping = interface_mapping
        self.external_endpoints = external_endpoints
        self.local_pox_enabled = local_pox_enabled

    def plan(
        self,
        spec: Any = None,
        *,
        interface_mapping: Mapping[str, Any] | None = None,
        external_endpoints: Mapping[str, Any] | None = None,
        local_pox_enabled: bool | None = None,
    ) -> TopologyPlan:
        configuration = spec if spec is not None else self.spec
        mapping = self.interface_mapping if interface_mapping is None else interface_mapping
        external = self.external_endpoints if external_endpoints is None else external_endpoints
        local = self.local_pox_enabled if local_pox_enabled is None else local_pox_enabled
        plan, diagnostics = self._build(configuration, mapping or {}, external, local)
        if diagnostics:
            raise TopologyPlanningError(diagnostics)
        return plan

    def plan_result(
        self,
        spec: Any = None,
        *,
        interface_mapping: Mapping[str, Any] | None = None,
        external_endpoints: Mapping[str, Any] | None = None,
        local_pox_enabled: bool | None = None,
    ) -> ValidationResult:
        """Compatibility result API used by validators and tooling."""

        try:
            plan = self.plan(
                spec,
                interface_mapping=interface_mapping,
                external_endpoints=external_endpoints,
                local_pox_enabled=local_pox_enabled,
            )
            return ValidationResult.success(plan)
        except TopologyPlanningError as exc:
            issues = tuple(
                ValidationIssue(item.code, item.message, field=item.field, value=item.value)
                for item in exc.diagnostics
            )
            return ValidationResult(value=None, issues=issues)

    build = plan
    resolve = plan
    from_spec = plan

    def validate(self, spec: Any = None, **kwargs: Any) -> tuple[PlanningDiagnostic, ...]:
        result = self.plan_result(spec, **kwargs)
        if result.ok:
            return ()
        return tuple(
            PlanningDiagnostic(item.code, item.message, field=item.field, value=item.value)
            for item in result.issues
        )

    def _build(
        self,
        configuration: Any,
        mapping: Mapping[str, Any],
        external_override: Mapping[str, Any] | None,
        local_pox: bool,
    ) -> tuple[TopologyPlan, tuple[PlanningDiagnostic, ...]]:
        if configuration is None:
            return TopologyPlan(), (
                PlanningDiagnostic(-11, "A topology specification is required", field="TOPOLOGY"),
            )
        spec = _attr(configuration, "SPEC", "spec", default=configuration)
        # RuntimeConfiguration carries a neutral SPEC.  A plain TopologySpec
        # has the lower-case fields directly.
        hosts = _items(_attr(spec, "mininet_hosts", "MNHOSTS", default=()))
        switches = _items(_attr(spec, "mininet_switches", "MNSWITCHES", default=()))
        controllers = _items(_attr(spec, "mininet_controllers", "MNCONTROLLER", default=()))
        ovs_switches = _items(_attr(spec, "mininet_ovs_switches", "MNOVSES", default=()))
        connections = _items(_attr(spec, "connections", "CONNECTIONS", default=()))
        if isinstance(configuration, TopologySpec) or _attr(configuration, "SPEC", default=None) is None:
            runtime_external = None
        else:
            runtime_external = self._runtime_external(configuration)
        external = dict(external_override or runtime_external or {})

        endpoint_data: dict[str, _EndpointData] = {}
        nodes: list[NodePlan] = []
        diagnostics: list[PlanningDiagnostic] = []

        def add_node(value: Any, kind: EndpointKind, field: str) -> None:
            ident = _attr(value, "id", "ID", default=value if isinstance(value, str) else None)
            if not isinstance(ident, str) or not ident:
                diagnostics.append(PlanningDiagnostic(-11, "Endpoint ID must be a non-empty string", field=field, value=ident))
                return
            if ident in endpoint_data:
                diagnostics.append(PlanningDiagnostic(-11, "Duplicate topology endpoint ID", field=field, value=ident))
                return
            endpoint = EndpointId(ident, kind)
            interfaces = _items(_attr(value, "interfaces", "INTERFACES", default=()))
            endpoint_data[ident] = _EndpointData(endpoint, interfaces)
            assignments = tuple(
                InterfaceAssignment(
                    endpoint,
                    str(_interface_value(item, "mac", "")),
                    _interface_value(item, "ip"),
                    _interface_value(item, "id"),
                    connected=False,
                )
                for item in interfaces
                if _interface_value(item, "mac") is not None
            ) if kind is EndpointKind.HOST else ()
            nodes.append(NodePlan(endpoint, assignments))

        for index, host in enumerate(hosts):
            add_node(host, EndpointKind.HOST, f"MININET.HOSTS[{index}]")
        for index, switch in enumerate(switches):
            add_node(switch, EndpointKind.SWITCH, f"MININET.SWITCHES[{index}]")
        for index, switch in enumerate(ovs_switches):
            add_node(switch, EndpointKind.OVS_SWITCH, f"MININET.OVSWITCHES[{index}]")

        # External descriptors are intentionally added after Mininet nodes;
        # they are endpoint references, not resources created by the adapter.
        for item in _items(_attr(spec, "vms", "VMS", default=())):
            self._add_external(item, endpoint_data, external, diagnostics, "VMS")
        for item in _items(_attr(spec, "containers", "CONTAINERS", default=())):
            self._add_external(item, endpoint_data, external, diagnostics, "CONTAINERS")
        for item in _items(_attr(spec, "vnfs", "VNFS", default=())):
            vnf_id = _attr(item, "id", "ID")
            vm = _attr(item, "vm", "VM", default=item)
            if isinstance(vm, str):
                vm = external.get(vnf_id, item)
            endpoint_data.setdefault(vnf_id, _EndpointData(EndpointId(vnf_id, EndpointKind.EXTERNAL), _items(_attr(vm, "interfaces", "INTERFACES", default=()))))
        for ident, runtime in external.items():
            if ident not in endpoint_data:
                value = _attr(runtime, "VM", "vm", default=runtime)
                endpoint_data[ident] = _EndpointData(EndpointId(ident, EndpointKind.EXTERNAL), _items(_attr(value, "INTERFACES", "interfaces", default=())))

        # Configured controllers are materialized in descriptor order.  A
        # local controller is synthesized only when regular switches need it.
        regular_switches = any(item.endpoint.kind is EndpointKind.SWITCH for item in endpoint_data.values())
        controller_plans: list[ControllerPlan] = []
        switch_controller_id: str | None = None
        if regular_switches:
            if local_pox:
                controller_plans.append(ControllerPlan("UNICTRL", "127.0.0.1", 6633, local=True))
                switch_controller_id = "UNICTRL"
            elif not controllers:
                diagnostics.append(PlanningDiagnostic(-4, "No controller configured for Mininet switches", field="MININET.CONTROLLERS"))
            else:
                switch_controller_id = _attr(controllers[0], "id", "ID")
        for index, controller in enumerate(controllers):
            ident = _attr(controller, "id", "ID")
            ip = _attr(controller, "ip", "IP")
            port = _attr(controller, "port", "PORT")
            if ident == "UNICTRL" and local_pox:
                diagnostics.append(PlanningDiagnostic(-9, "Controller ID UNICTRL is reserved", field=f"MININET.CONTROLLERS[{index}].ID", value=ident))
                continue
            try:
                port = int(port)
            except (TypeError, ValueError):
                port = 0
            controller_plans.append(ControllerPlan(ident, ip, port))

        # OVS references are validated here as a second safety net for direct
        # planner users who bypass PlatformParser.
        configured_ids = {str(_attr(item, "id", "ID")) for item in controllers}
        for index, switch in enumerate(ovs_switches):
            controller_id = _attr(switch, "controller", "CONTROLLER")
            if controller_id not in configured_ids:
                diagnostics.append(PlanningDiagnostic(-10, "OVS switch references an unknown controller", field=f"MININET.OVSWITCHES[{index}].CONTROLLER", value=controller_id))

        links: list[LinkPlan] = []
        assignments: list[InterfaceAssignment] = []
        used_interfaces: set[tuple[str, str]] = set()
        for index, connection in enumerate(connections):
            source_name = _connection_value(connection, "inout")
            target_name = _connection_value(connection, "outin")
            source_field = f"CONNECTIONS[{index}].IN/OUT"
            target_field = f"CONNECTIONS[{index}].OUT/IN"
            source = endpoint_data.get(source_name)
            target = endpoint_data.get(target_name)
            if source is None:
                diagnostics.append(PlanningDiagnostic(-12, "Connection references an unknown endpoint", field=source_field, value=source_name, connection_index=index))
            if target is None:
                diagnostics.append(PlanningDiagnostic(-13, "Connection references an unknown endpoint", field=target_field, value=target_name, connection_index=index))
            if source is None or target is None:
                continue
            if source.endpoint == target.endpoint:
                diagnostics.append(PlanningDiagnostic(-14, "A connection cannot link an endpoint to itself", field=f"CONNECTIONS[{index}]", value=source_name, connection_index=index))
                continue
            strategy = self._strategy(source.endpoint.kind, target.endpoint.kind)
            if strategy is None:
                diagnostics.append(PlanningDiagnostic(-3, "Connection endpoint combination is not supported", field=f"CONNECTIONS[{index}]", value={"IN/OUT": source_name, "OUT/IN": target_name}, connection_index=index))
                # In particular, external-to-external must fail without
                # attempting to resolve either side or touching host state.
                continue
            source_mac = _connection_value(connection, "inout_iface")
            target_mac = _connection_value(connection, "outin_iface")
            source_iface = self._resolve_interface(source, source_mac, index, "IN/OUTIFACE", mapping, diagnostics, used_interfaces)
            target_iface = self._resolve_interface(target, target_mac, index, "OUT/INIFACE", mapping, diagnostics, used_interfaces)
            if strategy in (LinkStrategy.HOST_HOST, LinkStrategy.HOST_SWITCH, LinkStrategy.SWITCH_SWITCH) and (source.endpoint.is_external or target.endpoint.is_external):
                diagnostics.append(PlanningDiagnostic(-3, "Connection endpoint combination is not supported", field=f"CONNECTIONS[{index}]", connection_index=index))
                continue
            self._validate_interface_shape(
                strategy,
                source,
                target,
                source_iface,
                target_iface,
                source_mac,
                target_mac,
                index,
                diagnostics,
            )
            if source_iface is not None:
                assignments.append(source_iface)
            if target_iface is not None:
                assignments.append(target_iface)
            if source_iface is not None and source.endpoint.kind is EndpointKind.HOST:
                source_node = next(item for item in nodes if item.id == source.endpoint.id)
                replaced = tuple(
                    source_iface if item.mac.lower() == source_iface.mac.lower() else item
                    for item in source_node.interfaces
                )
                source_node = NodePlan(source_node.endpoint, replaced, source_node.controller_id)
                nodes[nodes.index(next(item for item in nodes if item.id == source.endpoint.id))] = source_node
            if target_iface is not None and target.endpoint.kind is EndpointKind.HOST:
                target_node = next(item for item in nodes if item.id == target.endpoint.id)
                replaced = tuple(
                    target_iface if item.mac.lower() == target_iface.mac.lower() else item
                    for item in target_node.interfaces
                )
                target_node = NodePlan(target_node.endpoint, replaced, target_node.controller_id)
                nodes[nodes.index(next(item for item in nodes if item.id == target.endpoint.id))] = target_node
            links.append(LinkPlan(source.endpoint, target.endpoint, strategy, source_iface, target_iface, index))

        plan = TopologyPlan(tuple(nodes), tuple(links), tuple(controller_plans), tuple(assignments), switch_controller_id)
        return plan, tuple(diagnostics)

    @staticmethod
    def _strategy(source: EndpointKind, target: EndpointKind) -> LinkStrategy | None:
        if source is EndpointKind.HOST and target is EndpointKind.HOST:
            return LinkStrategy.HOST_HOST
        if source is EndpointKind.HOST and target.is_network_node:
            return LinkStrategy.HOST_SWITCH
        if source.is_network_node and target is EndpointKind.HOST:
            return LinkStrategy.HOST_SWITCH
        if source.is_network_node and target.is_network_node:
            return LinkStrategy.SWITCH_SWITCH
        if source is EndpointKind.HOST and target is EndpointKind.EXTERNAL:
            return LinkStrategy.HOST_EXTERNAL
        if source is EndpointKind.EXTERNAL and target is EndpointKind.HOST:
            return LinkStrategy.HOST_EXTERNAL
        if source.is_network_node and target is EndpointKind.EXTERNAL:
            return LinkStrategy.SWITCH_EXTERNAL
        if source is EndpointKind.EXTERNAL and target.is_network_node:
            return LinkStrategy.SWITCH_EXTERNAL
        return None

    @staticmethod
    def _validate_interface_shape(
        strategy,
        source,
        target,
        source_iface,
        target_iface,
        source_mac,
        target_mac,
        index,
        diagnostics,
    ):
        source_requires = False
        target_requires = False
        if strategy is LinkStrategy.HOST_HOST:
            source_requires = target_requires = True
        elif strategy is LinkStrategy.HOST_SWITCH:
            source_requires = source.endpoint.kind is EndpointKind.HOST
            target_requires = target.endpoint.kind is EndpointKind.HOST
        elif strategy is LinkStrategy.HOST_EXTERNAL:
            # Both sides carry an explicit interface in the legacy wire
            # format, regardless of which side is written first.
            source_requires = target_requires = True
        elif strategy is LinkStrategy.SWITCH_EXTERNAL:
            source_requires = source.endpoint.kind is EndpointKind.EXTERNAL
            target_requires = target.endpoint.kind is EndpointKind.EXTERNAL

        if source_requires and source_iface is None:
            diagnostics.append(
                PlanningDiagnostic(
                    -12,
                    "Connection endpoint requires an interface MAC",
                    field=f"CONNECTIONS[{index}].IN/OUTIFACE",
                    value=source_mac,
                    connection_index=index,
                )
            )
        if target_requires and target_iface is None:
            diagnostics.append(
                PlanningDiagnostic(
                    -13,
                    "Connection endpoint requires an interface MAC",
                    field=f"CONNECTIONS[{index}].OUT/INIFACE",
                    value=target_mac,
                    connection_index=index,
                )
            )

    @staticmethod
    def _resolve_interface(data, mac, index, field_name, mapping, diagnostics, used):
        endpoint = data.endpoint
        if mac is None:
            if endpoint.kind is EndpointKind.EXTERNAL:
                diagnostics.append(PlanningDiagnostic(-12 if field_name.startswith("IN") else -13, "External endpoint requires an interface MAC", field=f"CONNECTIONS[{index}].{field_name}", connection_index=index))
            return None
        interfaces = data.interfaces
        selected = next((item for item in interfaces if str(_interface_value(item, "mac", "")).lower() == str(mac).lower()), None)
        if selected is None:
            code = -12 if field_name.startswith("IN") else -13
            diagnostics.append(PlanningDiagnostic(code, f"Interface MAC does not belong to endpoint {endpoint.id}", field=f"CONNECTIONS[{index}].{field_name}", value=mac, connection_index=index))
            return None
        canonical_mac = _interface_value(selected, "mac", mac)
        mac_text = str(canonical_mac)
        if not _MAC_RE.fullmatch(mac_text) or mac_text.lower() == "00:00:00:00:00:00":
            code = -12 if field_name.startswith("IN") else -13
            diagnostics.append(PlanningDiagnostic(code, "Interface MAC is invalid or all-zero", field=f"CONNECTIONS[{index}].{field_name}", value=canonical_mac, connection_index=index))
            return None
        marker = (endpoint.id, str(canonical_mac).lower())
        if marker in used:
            diagnostics.append(PlanningDiagnostic(-11, "Endpoint interface is used by more than one connection", field=f"CONNECTIONS[{index}].{field_name}", value=mac, connection_index=index))
        used.add(marker)
        interface_id = _interface_value(selected, "id")
        bridge = None
        if endpoint.kind is EndpointKind.EXTERNAL:
            if not interface_id:
                diagnostics.append(PlanningDiagnostic(-1, "External endpoint interface has no bridge ID", field=f"CONNECTIONS[{index}].{field_name}", value=mac, connection_index=index))
            elif interface_id not in mapping:
                diagnostics.append(PlanningDiagnostic(-1, f"External interface {interface_id} is not available on the host", field=f"CONNECTIONS[{index}].{field_name}", value=interface_id, connection_index=index))
            else:
                bridge = mapping[interface_id] or interface_id
        ip = _interface_value(selected, "ip")
        if ip is not None:
            try:
                ip_interface(str(ip) if "/" in str(ip) else str(ip) + "/32")
            except ValueError:
                diagnostics.append(PlanningDiagnostic(-11, "Interface IP address or prefix is invalid", field=f"CONNECTIONS[{index}].{field_name}", value=ip, connection_index=index))
        return InterfaceAssignment(endpoint, mac_text, ip, interface_id, bridge, index, "source" if field_name.startswith("IN") else "target", True)

    @staticmethod
    def _add_external(item, endpoint_data, external, diagnostics, section):
        ident = _attr(item, "id", "ID")
        if not isinstance(ident, str) or not ident:
            return
        runtime = external.get(ident, item)
        value = _attr(runtime, "VM", "vm", default=runtime)
        interfaces = _items(_attr(value, "interfaces", "INTERFACES", default=()))
        endpoint_data.setdefault(ident, _EndpointData(EndpointId(ident, EndpointKind.EXTERNAL), interfaces))

    @staticmethod
    def _runtime_external(configuration):
        result: dict[str, Any] = {}
        for section in ("VMS", "CONTAINERS", "VNFS"):
            for item in _items(_attr(configuration, section, section.lower(), default=())):
                ident = _attr(item, "ID", "id")
                if section == "VNFS":
                    result[ident] = _attr(item, "VM", "vm", default=item)
                else:
                    result[ident] = item
        return result


__all__ = [
    "ControllerPlan", "EndpointId", "EndpointKind", "EndpointType",
    "InterfaceAssignment", "LinkKind", "LinkPlan", "LinkStrategy", "NodePlan",
    "PlanningDiagnostic", "TopologyPlan", "TopologyPlanner", "TopologyPlanningError",
    "PlanningError",
]
