from __future__ import annotations

from dataclasses import dataclass

import pytest

from niep.application.mininet_adapter import MininetTopologyAdapter
from niep.application.planner import TopologyPlanner
from niep.domain.spec import (
    ConnectionSpec,
    ContainerSpec,
    InterfaceSpec,
    MininetHostSpec,
    MininetSwitchSpec,
    TopologySpec,
)


@dataclass
class FakeInterface:
    name: str
    events: list
    mac: str | None = None
    ip: str | None = None

    def setMAC(self, mac):
        self.mac = mac
        self.events.append(("setMAC", self.name, mac))

    def setIP(self, ip):
        self.ip = ip
        self.events.append(("setIP", self.name, ip))

    def IP(self):
        return self.ip


class FakeNode:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def intf(self, interface):
        self.events.append(("intf", self.name, interface.name))
        return interface

    def cmd(self, command):
        self.events.append(("cmd", self.name, command))
        return ""


class FakeLink:
    def __init__(self, left, right, events):
        self.intf1 = FakeInterface(left.name + "-eth", events)
        self.intf2 = FakeInterface(right.name + "-eth", events)


class FakeMininet:
    def __init__(self, events, **_kwargs):
        self.events = events
        self.nodes = {}
        events.append(("Mininet",))

    def addHost(self, ident):
        self.events.append(("addHost", ident))
        self.nodes[ident] = FakeNode(ident, self.events)
        return self.nodes[ident]

    def addSwitch(self, ident):
        self.events.append(("addSwitch", ident))
        self.nodes[ident] = FakeNode(ident, self.events)
        return self.nodes[ident]

    def addController(self, ident, **_kwargs):
        self.events.append(("addController", ident))
        self.nodes[ident] = FakeNode(ident, self.events)
        return self.nodes[ident]

    def addLink(self, left, right):
        self.events.append(("addLink", left.name, right.name))
        return FakeLink(left, right, self.events)

    def build(self):
        self.events.append(("build",))


class FakeCleanup:
    def __init__(self, events):
        self.events = events

    def cleanup(self):
        self.events.append(("cleanup",))


class RuntimeHost:
    def __init__(self, ident, interfaces):
        self.ID = ident
        self.INTERFACES = [dict(item) for item in interfaces]
        self.ELEM = None


def host(ident, *interfaces):
    return MininetHostSpec(ident, tuple(interfaces))


def interface(mac, ip=None, ident=None):
    return InterfaceSpec(mac=mac, ip=ip, id=ident)


def make_adapter(events):
    return MininetTopologyAdapter(
        mininet_cls=lambda **kwargs: FakeMininet(events, **kwargs),
        cleanup_cls=lambda: FakeCleanup(events),
        intf_cls=lambda name, node=None, mac=None: _fake_intf(events, name, node, mac),
        remote_controller_cls=object,
    )


def _fake_intf(events, name, node, mac):
    events.append(("Intf", name, node.name, mac))
    return FakeInterface(name, events, mac=mac)


def build_plan(*, hosts=(), switches=(), containers=(), connections=(), mapping=None):
    spec = TopologySpec(
        "adapter",
        mininet_hosts=tuple(hosts),
        mininet_switches=tuple(switches),
        containers=tuple(containers),
        connections=tuple(connections),
    )
    return TopologyPlanner(spec, interface_mapping=mapping or {}).plan()


def runtime_hosts(*items):
    return {item.id: RuntimeHost(item.id, [iface.to_dict() for iface in item.interfaces]) for item in items}


def test_apply_orders_nodes_links_build_and_post_build_configuration():
    h1 = host(
        "h1",
        interface("02:00:00:00:00:01", "10.0.0.1/24"),
        interface("02:00:00:00:00:11", "10.0.0.11/24"),
    )
    switch = MininetSwitchSpec("s1")
    plan = build_plan(
        hosts=(h1,),
        switches=(switch,),
        connections=(ConnectionSpec("h1", "s1", "02:00:00:00:00:01"),),
    )
    events = []
    applied = make_adapter(events).apply(plan, runtime_nodes={"hosts": runtime_hosts(h1), "switches": {}})
    build_index = events.index(("build",))
    assert events.index(("addHost", "h1")) < events.index(("addLink", "h1", "s1")) < build_index
    assert any(event[0] == "setIP" and event[2] == "10.0.0.1/24" for event in events[build_index + 1 :])
    assert any(event[0] == "cmd" and "mn-eth0" in event[2] for event in events[build_index + 1 :])
    assert applied.hosts["h1"].name == "h1"


def test_h_h_binds_intf2_to_the_target_host():
    h1 = host("h1", interface("02:00:00:00:00:01", "10.0.0.1/24"))
    h2 = host("h2", interface("02:00:00:00:00:02", "10.0.0.2/24"))
    plan = build_plan(
        hosts=(h1, h2),
        connections=(ConnectionSpec("h1", "h2", h1.INTERFACES[0].mac, h2.INTERFACES[0].mac),),
    )
    events = []
    make_adapter(events).apply(plan, runtime_nodes={"hosts": runtime_hosts(h1, h2), "switches": {}})
    assert ("intf", "h1", "h1-eth") in events
    assert ("intf", "h2", "h2-eth") in events
    assert events.index(("intf", "h1", "h1-eth")) < events.index(("intf", "h2", "h2-eth"))


def test_n_h_binds_target_host_interface():
    h1 = host("h1", interface("02:00:00:00:00:01", "10.0.0.1/24"))
    plan = build_plan(
        hosts=(h1,),
        switches=(MininetSwitchSpec("s1"),),
        connections=(ConnectionSpec("s1", "h1", None, h1.INTERFACES[0].mac),),
    )
    events = []
    make_adapter(events).apply(plan, runtime_nodes={"hosts": runtime_hosts(h1), "switches": {}})
    assert ("intf", "h1", "h1-eth") in events
    assert ("setMAC", "h1-eth", h1.INTERFACES[0].mac) in events


@pytest.mark.parametrize("reverse", (False, True))
def test_h_e_and_e_h_use_mapped_virtual_interface(reverse):
    h1 = host("h1", interface("02:00:00:00:00:01", "10.0.0.1/24"))
    container = ContainerSpec(
        "c1", "c.json", "alpine", ["sleep"],
        interfaces=(interface("02:00:00:00:10:01", "10.0.0.2/24", "ct0"),),
    )
    connection = (
        ConnectionSpec("c1", "h1", container.INTERFACES[0].mac, h1.INTERFACES[0].mac)
        if reverse
        else ConnectionSpec("h1", "c1", h1.INTERFACES[0].mac, container.INTERFACES[0].mac)
    )
    plan = build_plan(hosts=(h1,), containers=(container,), connections=(connection,), mapping={"ct0": "veth-ct0"})
    events = []
    make_adapter(events).apply(plan, runtime_nodes={"hosts": runtime_hosts(h1), "switches": {}})
    assert ("Intf", "veth-ct0", "h1", h1.INTERFACES[0].mac) in events


@pytest.mark.parametrize("reverse", (False, True))
def test_s_e_and_e_s_use_external_interface_id_on_switch(reverse):
    switch = MininetSwitchSpec("s1")
    container = ContainerSpec(
        "c1", "c.json", "alpine", ["sleep"],
        interfaces=(interface("02:00:00:00:10:01", ident="ct0"),),
    )
    connection = (
        ConnectionSpec("c1", "s1", container.INTERFACES[0].mac, None)
        if reverse
        else ConnectionSpec("s1", "c1", None, container.INTERFACES[0].mac)
    )
    plan = build_plan(switches=(switch,), containers=(container,), connections=(connection,), mapping={"ct0": "veth-ct0"})
    events = []
    make_adapter(events).apply(plan, runtime_nodes={"hosts": {}, "switches": {}})
    assert ("Intf", "ct0", "s1", None) in events
