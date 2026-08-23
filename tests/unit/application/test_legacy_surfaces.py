"""Characterization tests for compatibility edges retained during 1.2.x."""

from niep.application.lifecycle import OperationStep, OperationStepState
from niep.application.planner import PlanningDiagnostic
from niep.runtime.contracts import legacy_status, normalize_status
from niep.runtime.errors import RuntimeFailure


def test_legacy_status_helpers_remain_identical_at_adapter_edges() -> None:
    assert normalize_status is legacy_status
    assert [legacy_status(value) for value in (None, True, False, 7)] == [0, 0, -1, 7]


def test_planning_diagnostic_legacy_code_alias_preserves_typed_code() -> None:
    diagnostic = PlanningDiagnostic(code=-11, message="invalid connection")
    assert diagnostic.legacy_code == diagnostic.code == diagnostic.status


def test_operation_step_legacy_aliases_preserve_new_lifecycle_fields() -> None:
    step = OperationStep("create", resource_type="vm", resource_id="vm-1")
    assert step.name == step.operation == "create"
    assert step.resource == step.resource_type == "vm"
    assert step.status is step.state is OperationStepState.PENDING

    step.name = "remove"
    step.status = OperationStepState.COMPLETED
    assert step.operation == "remove"
    assert step.state is OperationStepState.COMPLETED


def test_runtime_failure_legacy_resource_aliases_preserve_typed_fields() -> None:
    failure = RuntimeFailure("create", resource_type="vm", resource_id="vm-1")
    assert failure.type == failure.resource_type == "vm"
    assert failure.id == failure.resource_id == "vm-1"
