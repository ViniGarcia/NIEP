from __future__ import annotations

import pytest

from niep.application.planner import (
    EndpointKind,
    LinkStrategy,
    TopologyPlanner,
    TopologyPlanningError,
)
from niep.domain.spec import (
    ConnectionSpec,
    ContainerSpec,
    InterfaceSpec,
    MininetHostSpec,
    MininetSwitchSpec,
    TopologySpec,
)


def host(name, *interfaces):
    return MininetHostSpec(name, tuple(interfaces))


def iface(mac, ip=None, ident=None):
    return InterfaceSpec(mac=mac, ip=ip, id=ident)


def plan_for(*, hosts=(), switches=(), ovs=(), connections=(), containers=(), mapping=None):
    spec = TopologySpec(
        "planner",
        containers=tuple(containers),
        mininet_hosts=tuple(hosts),
        mininet_switches=tuple(switches),
        mininet_ovs_switches=tuple(ovs),
        connections=tuple(connections),
    )
    return TopologyPlanner(spec, interface_mapping=mapping or {}).plan()


def test_matrix_covers_all_supported_link_strategies_in_descriptor_order():
    h1 = host("h1", iface("02:00:00:00:00:01", "10.0.0.1/24"))
    h2 = host("h2", iface("02:00:00:00:00:02", "10.0.0.2/24"))
    h3 = host("h3", iface("02:00:00:00:00:03", "10.0.0.3/24"))
    switches = (MininetSwitchSpec("s1"), MininetSwitchSpec("s2"))
    container = ContainerSpec(
        "c1", "container.json", "alpine", ["sleep"],
        interfaces=(iface("02:00:00:00:10:01", "10.0.0.4/24", "ct-c1"),),
    )
    links = (
        ConnectionSpec("h1", "h2", h1.INTERFACES[0].mac, h2.INTERFACES[0].mac),
        ConnectionSpec("h2", "s1", h2.INTERFACES[0].mac),
        ConnectionSpec("s1", "s2"),
        ConnectionSpec("h3", "c1", h3.INTERFACES[0].mac, container.INTERFACES[0].mac),
        ConnectionSpec("s2", "c1", None, container.INTERFACES[0].mac),
    )
    # A given descriptor interface is intentionally used once per connection;
    # use distinct h2/c1 interfaces for the full matrix.
    h2 = host(
        "h2",
        iface("02:00:00:00:00:02", "10.0.0.2/24"),
        iface("02:00:00:00:00:22", "10.0.0.22/24"),
    )
    container = ContainerSpec(
        "c1", "container.json", "alpine", ["sleep"],
        interfaces=(
            iface("02:00:00:00:10:01", "10.0.0.4/24", "ct-c1"),
            iface("02:00:00:00:10:02", "10.0.0.5/24", "ct-c2"),
        ),
    )
    links = (
        ConnectionSpec("h1", "h2", h1.INTERFACES[0].mac, h2.INTERFACES[0].mac),
        ConnectionSpec("h2", "s1", h2.INTERFACES[1].mac),
        ConnectionSpec("s1", "s2"),
        ConnectionSpec("h3", "c1", h3.INTERFACES[0].mac, container.INTERFACES[0].mac),
        ConnectionSpec("s2", "c1", None, container.INTERFACES[1].mac),
    )
    plan = plan_for(hosts=(h1, h2, h3), switches=switches, connections=links,
                    containers=(container,), mapping={"ct-c1": "ct-c1", "ct-c2": "ct-c2"})
    assert [link.strategy for link in plan.links] == [
        LinkStrategy.HOST_HOST,
        LinkStrategy.HOST_SWITCH,
        LinkStrategy.SWITCH_SWITCH,
        LinkStrategy.HOST_EXTERNAL,
        LinkStrategy.SWITCH_EXTERNAL,
    ]
    assert plan.links[0].source_interface.endpoint.kind is EndpointKind.HOST
    assert plan.links[0].target_interface.endpoint.id == "h2"


def test_plan_is_pure_and_repeatable():
    spec = TopologySpec(
        "pure",
        mininet_hosts=(host("h1", iface("02:00:00:00:00:01", "10.1.0.1/24")),),
        mininet_switches=(MininetSwitchSpec("s1"),),
        connections=(ConnectionSpec("h1", "s1", "02:00:00:00:00:01"),),
    )
    first = TopologyPlanner(spec).plan()
    second = TopologyPlanner(spec).plan()
    assert first == second
    assert spec.mininet_hosts[0].ELEM is None
    assert first.to_dict() == second.to_dict()


@pytest.mark.parametrize(
    "connection, code",
    [
        (ConnectionSpec("missing", "s1"), -12),
        (ConnectionSpec("h1", "missing", "02:00:00:00:00:01"), -13),
        (ConnectionSpec("h1", "h1", "02:00:00:00:00:01", "02:00:00:00:00:01"), -14),
    ],
)
def test_invalid_references_fail_before_application(connection, code):
    with pytest.raises(TopologyPlanningError) as raised:
        plan_for(hosts=(host("h1", iface("02:00:00:00:00:01")),), switches=(MininetSwitchSpec("s1"),), connections=(connection,))
    assert raised.value.status == code
    assert raised.value.diagnostics[0].connection_index == 0


def test_external_to_external_is_rejected_without_resolving_interfaces():
    left = ContainerSpec("left", "left.json", "alpine", ["sleep"], interfaces=(iface("02:00:00:00:10:01", ident="left0"),))
    right = ContainerSpec("right", "right.json", "alpine", ["sleep"], interfaces=(iface("02:00:00:00:10:02", ident="right0"),))
    with pytest.raises(TopologyPlanningError) as raised:
        plan_for(containers=(left, right), connections=(ConnectionSpec("left", "right", left.INTERFACES[0].mac, right.INTERFACES[0].mac),), mapping={})
    assert raised.value.status == -3


@pytest.mark.parametrize(
    "connection, code",
    [
        (ConnectionSpec("h1", "c1", None, "02:00:00:00:10:01"), -12),
        (ConnectionSpec("h1", "c1", "02:00:00:00:00:01", None), -13),
        (ConnectionSpec("c1", "h1", None, "02:00:00:00:00:01"), -12),
        (ConnectionSpec("c1", "h1", "02:00:00:00:10:01", None), -13),
    ],
)
def test_host_external_requires_both_directional_assignments(connection, code):
    container = ContainerSpec(
        "c1", "c.json", "alpine", ["sleep"],
        interfaces=(iface("02:00:00:00:10:01", "10.2.0.2/24", "ct0"),),
    )
    with pytest.raises(TopologyPlanningError) as raised:
        plan_for(
            hosts=(host("h1", iface("02:00:00:00:00:01", "10.2.0.1/24")),),
            containers=(container,),
            connections=(connection,),
            mapping={"ct0": "veth-ct0"},
        )
    assert raised.value.status == code


def test_missing_external_bridge_is_a_planning_diagnostic():
    container = ContainerSpec("c1", "c.json", "alpine", ["sleep"], interfaces=(iface("02:00:00:00:10:01", "10.2.0.2/24", "ct0"),))
    with pytest.raises(TopologyPlanningError) as missing:
        plan_for(hosts=(host("h1", iface("02:00:00:00:00:01", "10.2.0.1/24")),), containers=(container,), connections=(ConnectionSpec("h1", "c1", "02:00:00:00:00:01", container.INTERFACES[0].mac),), mapping={})
    assert missing.value.status == -1


def test_l2_links_do_not_require_matching_ip_networks_or_prefixes():
    plan = plan_for(
        hosts=(
            host("h1", iface("02:00:00:00:00:01", "10.2.0.1/24")),
            host("h2", iface("02:00:00:00:00:02", "10.2.1.2/16")),
        ),
        connections=(ConnectionSpec("h1", "h2", "02:00:00:00:00:01", "02:00:00:00:00:02"),),
    )
    assert plan.links[0].strategy is LinkStrategy.HOST_HOST
