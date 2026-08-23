import pytest

from niep.application.lifecycle import (
    InvalidTopologyTransition,
    TOPOLOGY_TRANSITIONS,
    TopologyState,
    TopologyStateMachine,
)


def test_transition_table_contains_every_public_state():
    assert set(TOPOLOGY_TRANSITIONS) == set(TopologyState)
    assert all(isinstance(targets, frozenset) for targets in TOPOLOGY_TRANSITIONS.values())


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (source, target)
        for source, targets in TOPOLOGY_TRANSITIONS.items()
        for target in targets
    ],
)
def test_every_declared_transition_is_accepted(source, target):
    machine = TopologyStateMachine(source)
    assert machine.can_transition(target)
    assert machine.transition(target) == target


@pytest.mark.parametrize(
    ("source", "target"),
    [
        (TopologyState.UNDEFINED, TopologyState.UP),
        (TopologyState.DEFINED, TopologyState.UP),
        (TopologyState.UP, TopologyState.DEFINED),
        (TopologyState.STOPPING, TopologyState.STARTING),
        (TopologyState.DESTROYED, TopologyState.UP),
    ],
)
def test_invalid_transition_is_explicit(source, target):
    machine = TopologyStateMachine(source)
    with pytest.raises(InvalidTopologyTransition):
        machine.transition(target)
