"""Contract tests for the typed topology port and its legacy adapter."""

import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from niep.application.executor_port import LegacyExecutorAdapter
from niep.application.lifecycle import OperationJournal, OperationStep, OperationStepState, TopologyState
from niep.application.topology_service import TopologyService


def _legacy(*, journal=None):
    configuration = SimpleNamespace(
        SFCS=[SimpleNamespace(ID="sfc-1")],
    )
    return SimpleNamespace(
        lifecycle_state=TopologyState.DEFINED,
        STATUS=0,
        DETAIL="",
        CLEANUP_REQUIRED=False,
        CLEANUP_ERRORS=[],
        JOURNAL=journal if journal is not None else OperationJournal(),
        CONFIGURATION=configuration,
        VMS={"vm-1": object()},
        CONTAINERS={"container-1": object()},
        VNFS={"vnf-1": object()},
        NET=None,
        _PERSISTENT_STATE_COMPLETED=set(),
    )


@pytest.mark.parametrize(
    ("journal", "expected_incomplete"),
    [
        (OperationJournal(), False),
        (
            OperationJournal(
                [OperationStep("done", state=OperationStepState.COMPLETED)]
            ),
            False,
        ),
        (
            OperationJournal([OperationStep("pending")]),
            True,
        ),
    ],
)
def test_snapshot_represents_journal_progress_not_just_length(journal, expected_incomplete):
    snapshot = LegacyExecutorAdapter(_legacy(journal=journal)).snapshot()
    assert snapshot.attached is True
    assert snapshot.lifecycle_state is TopologyState.DEFINED
    assert snapshot.journal_length == len(journal)
    assert snapshot.journal_incomplete is expected_incomplete
    assert snapshot.vm_ids == ("vm-1",)
    assert snapshot.container_ids == ("container-1",)
    assert snapshot.vnf_ids == ("vnf-1",)
    assert snapshot.sfc_ids == ("sfc-1",)


def test_adapter_supports_lowercase_legacy_journal_and_persistent_ledger_port():
    legacy = _legacy()
    del legacy.JOURNAL
    legacy.journal = OperationJournal([OperationStep("pending")])
    adapter = LegacyExecutorAdapter(legacy)
    key = ("vm_image", "vm-1", "remove_persistent_state")

    assert adapter.snapshot().journal_incomplete is True
    assert adapter.persistent_done(key) is False
    adapter.mark_persistent_done(key)
    assert adapter.persistent_done(key) is True


@pytest.mark.parametrize("journal", [[], [object()]])
def test_adapter_uses_collection_length_when_legacy_journal_has_no_progress_property(journal):
    legacy = _legacy()
    del legacy.JOURNAL
    legacy.journal = journal
    snapshot = LegacyExecutorAdapter(legacy).snapshot()
    assert snapshot.journal_length == len(journal)
    assert snapshot.journal_incomplete is bool(journal)


def test_topology_service_accepts_a_typed_port_without_legacy_field_access():
    class Port:
        def snapshot(self):
            return type("Snapshot", (), {"attached": False})()

    service = TopologyService(topology_port=Port())
    assert service.is_defined() is False


@pytest.mark.parametrize("up_result", [0, 7, None])
def test_legacy_executor_without_lifecycle_or_status_uses_operation_result(up_result):
    class Legacy:
        def topologyUp(self):
            return up_result

        def topologyDown(self):
            return 0

        def rollbackFailedStart(self):
            return []

    service = TopologyService()
    service.executor = Legacy()
    result = service.up()

    if up_result == 0:
        assert result.ok is True
        assert result.code.value == "topology_up"
        assert service.state is TopologyState.UP
    else:
        assert result.ok is False
        assert result.code.value == "topology_up_failed"
        assert service.state is TopologyState.UNDEFINED


def test_legacy_status_none_is_distinct_from_an_absent_status_attribute():
    class Legacy:
        STATUS = None

        def topologyUp(self):
            return 0

        def rollbackFailedStart(self):
            return []

    service = TopologyService()
    service.executor = Legacy()
    result = service.up()

    assert result.ok is False
    assert result.code.value == "topology_up_failed"
    assert service.state is TopologyState.UNDEFINED


def test_legacy_field_names_are_confined_to_the_adapter():
    forbidden = {
        "STATUS",
        "DETAIL",
        "NET",
        "VMS",
        "VNFS",
        "CONTAINERS",
        "CONFIGURATION",
        "CLEANUP_REQUIRED",
        "CLEANUP_ERRORS",
        "JOURNAL",
    }
    adapter_tree = ast.parse(Path("niep/application/executor_port.py").read_text())
    service_tree = ast.parse(Path("niep/application/service.py").read_text())
    topology_tree = ast.parse(Path("niep/application/topology_service.py").read_text())
    session_tree = ast.parse(Path("niep/application/session.py").read_text())

    adapter_attrs = {
        node.attr for node in ast.walk(adapter_tree) if isinstance(node, ast.Attribute)
    }
    assert forbidden - {"JOURNAL"} <= adapter_attrs
    assert '"JOURNAL"' in Path("niep/application/executor_port.py").read_text()
    for tree in (service_tree, session_tree):
        attrs = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
        assert not forbidden.intersection(attrs)
    topology_attrs = {
        node.attr
        for node in ast.walk(topology_tree)
        if isinstance(node, ast.Attribute)
    }
    # The parser is a separate validated input boundary and legitimately has
    # a STATUS field; the service must nevertheless not dereference a raw
    # executor attribute or NET.
    assert "NET" not in topology_attrs
    assert not any(
        isinstance(node, ast.Attribute)
        and node.attr == "executor"
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
        for node in ast.walk(topology_tree)
    )
