from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

import niep.application.executer as executer_module
from niep.application.executer import Executer
from niep.application.mininet_adapter import (
    AppliedTopology,
    MininetTopologyAdapter,
    TopologyApplicationError,
)
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


def test_apply_failure_after_local_pox_returns_partial_handles_and_original_cause():
    switch = MininetSwitchSpec("s1")
    plan = build_plan(switches=(switch,))
    events = []
    pox = object()

    class FailingControllerMininet(FakeMininet):
        def addController(self, ident, **_kwargs):
            self.events.append(("addController", ident))
            raise RuntimeError("controller creation failed")

    adapter = MininetTopologyAdapter(
        mininet_cls=lambda **kwargs: FailingControllerMininet(events, **kwargs),
        cleanup_cls=lambda: FakeCleanup(events),
        intf_cls=lambda name, node=None, mac=None: _fake_intf(events, name, node, mac),
        remote_controller_cls=object,
        local_pox=lambda: pox,
    )

    with pytest.raises(TopologyApplicationError) as raised:
        adapter.apply(plan, runtime_nodes={"hosts": {}, "switches": {}})

    error = raised.value
    assert error.partial.net is not None
    assert error.partial.pox is pox
    assert error.partial.switches["s1"].name == "s1"
    record = error.to_dict()
    assert record["message"] == "controller creation failed"
    assert record["cause"]["message"] == "controller creation failed"


def test_apply_failure_after_nodes_and_links_returns_partial_bindings():
    h1 = host("h1", interface("02:00:00:00:00:01"))
    switch = MininetSwitchSpec("s1")
    plan = build_plan(
        hosts=(h1,),
        switches=(switch,),
        connections=(ConnectionSpec("h1", "s1", h1.INTERFACES[0].mac),),
    )
    events = []

    class FailingLinkMininet(FakeMininet):
        def addLink(self, left, right):
            self.events.append(("addLink", left.name, right.name))
            raise RuntimeError("link creation failed")

    adapter = MininetTopologyAdapter(
        mininet_cls=lambda **kwargs: FailingLinkMininet(events, **kwargs),
        cleanup_cls=lambda: FakeCleanup(events),
        intf_cls=lambda name, node=None, mac=None: _fake_intf(events, name, node, mac),
        remote_controller_cls=object,
    )

    with pytest.raises(TopologyApplicationError) as raised:
        adapter.apply(
            plan,
            runtime_nodes={"hosts": runtime_hosts(h1), "switches": {}},
        )

    partial = raised.value.partial
    assert partial.hosts["h1"].name == "h1"
    assert partial.switches["s1"].name == "s1"
    assert partial.net is not None
    assert raised.value.to_dict()["cause"]["message"] == "link creation failed"


def test_executor_adopts_partial_topology_before_best_effort_rollback(monkeypatch):
    calls = []

    class Net:
        def stop(self):
            calls.append("net")
            return 0

    class Infrastructure:
        def start_local_pox(self):
            return object()

        def stop_process(self, _process):
            calls.append("pox")
            return 0

    configuration = SimpleNamespace(
        STATUS=0,
        ID="partial-topology",
        VMS=[],
        VNFS=[],
        CONTAINERS=[],
        SFCS=[],
        MNHOSTS=[],
        MNSWITCHES=[],
        MNCONTROLLER=[],
        MNOVSES=[],
    )
    executor = Executer(configuration, infrastructure=Infrastructure())
    executor._MININET_PLAN = SimpleNamespace(switch_controller_id=None)
    partial = AppliedTopology(net=Net(), pox=object())

    class FailingAdapter:
        def __init__(self, **_kwargs):
            pass

        def apply(self, *_args, **_kwargs):
            raise TopologyApplicationError(RuntimeError("late link failure"), partial)

    monkeypatch.setattr(executer_module, "MininetTopologyAdapter", FailingAdapter)

    with pytest.raises(TopologyApplicationError) as raised:
        executor._mininet_apply()

    assert executor.NET is partial.net
    assert executor.POX is partial.pox
    assert executor.DETAIL == "late link failure"
    assert raised.value.to_dict()["cause"]["message"] == "late link failure"
    assert executor._compensate_mininet() == 0
    assert calls == ["net", "pox"]


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
