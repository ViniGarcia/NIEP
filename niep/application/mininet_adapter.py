"""Imperative Mininet adapter for :mod:`niep.application.planner` plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

from .planner import EndpointKind, InterfaceAssignment, LinkPlan, LinkStrategy, TopologyPlan
from niep.runtime.errors import RuntimeFailure


@dataclass
class AppliedTopology:
    """Runtime handles produced by applying a validated plan."""

    net: Any
    hosts: dict[str, Any] = field(default_factory=dict)
    switches: dict[str, Any] = field(default_factory=dict)
    ovs_switches: dict[str, Any] = field(default_factory=dict)
    controllers: dict[str, Any] = field(default_factory=dict)
    pox: Any = None
    switch_controller_id: str | None = None
    runtime_hosts: dict[str, Any] = field(default_factory=dict)
    host_interfaces: dict[tuple[str, str], Any] = field(default_factory=dict)

    @property
    def NET(self):
        return self.net


class TopologyApplicationError(RuntimeFailure):
    """Typed adapter failure carrying resources created before the failure."""

    def __init__(self, cause: BaseException, partial: AppliedTopology):
        self.partial = partial
        super().__init__(
            "mininet.apply",
            "mininet",
            "topology",
            cause=cause,
        )


# Compatibility spelling for callers that scope the error to Mininet.
MininetApplyError = TopologyApplicationError


class MininetTopologyAdapter:
    """Apply a :class:`TopologyPlan` with explicitly injected Mininet APIs.

    The default imports are intentionally lazy.  Host-only code can import and
    unit-test this module without Mininet installed, while the executor passes
    its already imported symbols (which also keeps existing monkeypatches
    working).
    """

    def __init__(
        self,
        *,
        mininet_cls: Callable[..., Any] | None = None,
        cleanup_cls: Callable[..., Any] | None = None,
        intf_cls: Callable[..., Any] | None = None,
        remote_controller_cls: Callable[..., Any] | None = None,
        local_pox: Callable[[], Any] | None = None,
        # Factory spellings make the seam convenient for tiny unit-test fakes.
        mininet_factory: Callable[..., Any] | None = None,
        cleanup_factory: Callable[..., Any] | None = None,
        intf: Callable[..., Any] | None = None,
        remote_controller: Callable[..., Any] | None = None,
    ) -> None:
        self.mininet_cls = mininet_cls or mininet_factory or self._load("Mininet", "mininet.net")
        self.cleanup_cls = cleanup_cls or cleanup_factory or self._load("Cleanup", "mininet.clean")
        self.intf_cls = intf_cls or intf or self._load("Intf", "mininet.link")
        self.remote_controller_cls = remote_controller_cls or remote_controller or self._load("RemoteController", "mininet.node")
        self.local_pox = local_pox

    @staticmethod
    def _load(name: str, module: str):
        try:
            imported = __import__(module, fromlist=[name])
            return getattr(imported, name)
        except (ImportError, AttributeError) as exc:
            raise RuntimeError("Mininet is unavailable; inject adapter dependencies") from exc

    def apply(
        self,
        plan: TopologyPlan,
        *,
        runtime_configuration: Any = None,
        runtime_nodes: Mapping[str, Mapping[str, Any]] | None = None,
    ) -> AppliedTopology:
        if not plan.ok:
            raise ValueError("cannot apply an invalid topology plan: " + plan.detail())
        net = self.mininet_cls(topo=None, build=False)
        applied = AppliedTopology(
            net=net,
            switch_controller_id=plan.switch_controller_id,
        )
        try:
            runtime = runtime_nodes or self._runtime_nodes(runtime_configuration)
            applied.runtime_hosts = dict(runtime.get("hosts", {}))
            self.cleanup_cls().cleanup()

            # Preserve the legacy creation order: hosts, regular switches,
            # controllers, then OVS switches.  This affects generated
            # interface names and is part of the public compatibility
            # surface.
            for node in plan.nodes:
                if node.endpoint.kind is EndpointKind.HOST:
                    elem = net.addHost(node.id)
                    applied.hosts[node.id] = elem
                    self._bind(runtime.get("hosts", {}).get(node.id), elem)
            for node in plan.nodes:
                if node.endpoint.kind is EndpointKind.SWITCH:
                    elem = net.addSwitch(node.id)
                    applied.switches[node.id] = elem
                    self._bind(runtime.get("switches", {}).get(node.id), elem)
            for controller in plan.controllers:
                if controller.local and self.local_pox is not None:
                    applied.pox = self.local_pox()
                elem = net.addController(
                    controller.id,
                    controller=self.remote_controller_cls,
                    ip=controller.ip,
                    port=controller.port,
                )
                applied.controllers[controller.id] = elem
                self._bind(runtime.get("controllers", {}).get(controller.id), elem)
            for node in plan.nodes:
                if node.endpoint.kind is EndpointKind.OVS_SWITCH:
                    elem = net.addSwitch(node.id)
                    applied.ovs_switches[node.id] = elem
                    self._bind(runtime.get("ovs_switches", {}).get(node.id), elem)

            for link in plan.links:
                self._apply_link(link, applied)
            net.build()
            self._configure_hosts(plan, applied, runtime)
            return applied
        except Exception as exc:
            # The caller must be able to compensate handles allocated before
            # any node, link, controller, or post-build configuration failed.
            # Keep the original exception as the typed cause and expose the
            # partial topology for deterministic best-effort cleanup.
            raise TopologyApplicationError(exc, applied) from exc

    def _apply_link(self, link: LinkPlan, applied: AppliedTopology) -> None:
        if link.strategy in (LinkStrategy.HOST_HOST, LinkStrategy.HOST_SWITCH, LinkStrategy.SWITCH_SWITCH):
            source_elem = self._node(link.source.kind, link.source.id, applied)
            target_elem = self._node(link.target.kind, link.target.id, applied)
            mininet_link = applied.net.addLink(source_elem, target_elem)
            self._bind_link_interface(link.source_interface, mininet_link, "intf1", source_elem, applied)
            self._bind_link_interface(link.target_interface, mininet_link, "intf2", target_elem, applied)
            return
        if link.strategy in (LinkStrategy.HOST_EXTERNAL, LinkStrategy.SWITCH_EXTERNAL):
            network_assignment, host_assignment = self._external_sides(link)
            network_endpoint = link.target if link.source.kind is EndpointKind.EXTERNAL else link.source
            network_elem = self._node(network_endpoint.kind, network_endpoint.id, applied)
            if host_assignment is None:
                # A switch consumes the descriptor's bridge name (brName in
                # the legacy path), while a host consumes the mapped physical
                # interface.  Keeping both values in InterfaceAssignment is
                # what prevents the two cases from being conflated.
                self.intf_cls(network_assignment.interface_id or network_assignment.bridge, node=network_elem)
            else:
                host_iface = self.intf_cls(network_assignment.bridge, node=network_elem, mac=host_assignment.mac)
                self._bind_interface(host_assignment, host_iface, applied)
            return
        raise ValueError("unknown link strategy: " + str(link.strategy))

    @staticmethod
    def _external_sides(link: LinkPlan) -> tuple[InterfaceAssignment, InterfaceAssignment | None]:
        source_external = link.source.kind is EndpointKind.EXTERNAL
        external_assignment = link.source_interface if source_external else link.target_interface
        host_assignment = link.target_interface if source_external else link.source_interface
        # A switch external link has no network-side host assignment.  The
        # network side is still the side carrying the external bridge.
        if external_assignment is None:
            raise ValueError("external links require a resolved external interface")
        if host_assignment is not None and host_assignment.endpoint.kind is not EndpointKind.HOST:
            host_assignment = None
        return external_assignment, host_assignment

    @staticmethod
    def _node(kind: EndpointKind, ident: str, applied: AppliedTopology) -> Any:
        if kind is EndpointKind.HOST:
            return applied.hosts[ident]
        if kind is EndpointKind.SWITCH:
            return applied.switches[ident]
        if kind is EndpointKind.OVS_SWITCH:
            return applied.ovs_switches[ident]
        raise KeyError("external endpoint has no Mininet node: " + ident)

    def _bind_link_interface(self, assignment, mininet_link, attr, node, applied):
        if assignment is None or assignment.endpoint.kind is not EndpointKind.HOST:
            return
        raw = getattr(mininet_link, attr)
        iface = node.intf(raw)
        iface.setMAC(assignment.mac)
        self._bind_interface(assignment, iface, applied)

    @staticmethod
    def _bind_interface(assignment: InterfaceAssignment, iface: Any, applied: AppliedTopology) -> None:
        # The mutable runtime host copy stores interfaces as dictionaries.
        applied.host_interfaces[(assignment.endpoint.id, assignment.mac.lower())] = iface
        host = applied.runtime_hosts.get(assignment.endpoint.id)
        if host is None:
            return
        interfaces = getattr(host, "INTERFACES", ())
        for item in interfaces:
            mac = item.get("MAC") if isinstance(item, Mapping) else getattr(item, "MAC", None)
            if str(mac).lower() == assignment.mac.lower():
                if isinstance(item, dict):
                    item["ELEM"] = iface
                else:
                    try:
                        item.ELEM = iface
                    except AttributeError:
                        pass
                return

    def _configure_hosts(self, plan: TopologyPlan, applied: AppliedTopology, runtime) -> None:
        assignments = {
            (item.endpoint.id, item.mac.lower()): item
            for item in plan.assignments
            if item.endpoint.kind is EndpointKind.HOST and item.connected
        }
        for node in plan.nodes:
            if node.endpoint.kind is not EndpointKind.HOST:
                continue
            runtime_host = runtime.get("hosts", {}).get(node.id)
            # NodePlan carries every declared interface, including an
            # unconnected interface which must become a deterministic dummy.
            interfaces = node.interfaces
            dummy = 0
            for item in interfaces:
                mac = item.mac
                ip = item.ip
                assignment = assignments.get((node.id, str(mac).lower())) if item.connected else None
                if assignment is not None:
                    runtime_iface = next(
                        (
                            raw.get("ELEM") if isinstance(raw, Mapping) else getattr(raw, "ELEM", None)
                            for raw in getattr(runtime_host, "INTERFACES", ())
                            if (raw.get("MAC") if isinstance(raw, Mapping) else getattr(raw, "MAC", None))
                            and str(raw.get("MAC") if isinstance(raw, Mapping) else getattr(raw, "MAC", None)).lower() == str(mac).lower()
                        ),
                        None,
                    )
                    iface = runtime_iface or applied.host_interfaces.get((node.id, str(mac).lower()))
                    if ip is not None and iface is not None:
                        iface.setIP(ip)
                    elif iface is not None and iface.IP() is not None:
                        applied.hosts[node.id].cmd("sudo ip addr flush " + str(iface.name))
                    continue
                name = "mn-eth" + str(dummy)
                applied.hosts[node.id].cmd("sudo ip link add " + name + " address " + str(mac) + " type dummy")
                if ip is not None:
                    applied.hosts[node.id].cmd("sudo ip addr add " + str(ip) + " dev " + name)
                applied.hosts[node.id].cmd("sudo ifconfig " + name + " up")
                dummy += 1

    @staticmethod
    def _bind(runtime_object: Any, elem: Any) -> None:
        if runtime_object is None:
            return
        try:
            runtime_object.ELEM = elem
        except (AttributeError, TypeError):
            pass

    @staticmethod
    def _runtime_nodes(configuration: Any) -> dict[str, dict[str, Any]]:
        if configuration is None:
            return {"hosts": {}, "switches": {}, "controllers": {}, "ovs_switches": {}}
        def indexed(*names):
            result = {}
            for name in names:
                values = getattr(configuration, name, ())
                for value in values or ():
                    ident = getattr(value, "ID", getattr(value, "id", None))
                    if ident is not None:
                        result[ident] = value
            return result
        return {
            "hosts": indexed("MNHOSTS", "mininet_hosts"),
            "switches": indexed("MNSWITCHES", "mininet_switches"),
            "controllers": indexed("MNCONTROLLER", "mininet_controllers"),
            "ovs_switches": indexed("MNOVSES", "mininet_ovs_switches"),
        }


__all__ = [
    "AppliedTopology",
    "MininetApplyError",
    "MininetTopologyAdapter",
    "TopologyApplicationError",
]
