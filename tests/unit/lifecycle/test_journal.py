import json

from niep.application.lifecycle import (
    OperationJournal,
    OperationStep,
    OperationStepState,
    operation_key,
)


def test_key_is_stable_and_successful_steps_are_not_repeated():
    calls = []
    journal = OperationJournal()
    first = journal.add(
        OperationStep(
            "create",
            resource_type="vm",
            resource_id="vm-1",
            apply=lambda: calls.append("create") or 0,
        )
    )
    second = journal.add(
        OperationStep(
            "up",
            resource_type="vm",
            resource_id="vm-1",
            apply=lambda: calls.append("up") or 0,
            depends_on=(first.key,),
        )
    )

    assert first.key == operation_key("create", "vm", "vm-1")
    assert first.key == OperationStep("create", "vm", "vm-1").key
    assert journal.run()
    assert journal.run()
    assert calls == ["create", "up"]
    assert first.attempts == second.attempts == 1


def test_failed_step_can_retry_without_repeating_completed_dependency():
    calls = []
    fail_once = {"value": True}
    journal = OperationJournal()
    first = journal.add(
        OperationStep("infra", resource_type="infrastructure", apply=lambda: calls.append("infra") or 0)
    )

    def flaky():
        calls.append("vm")
        if fail_once.pop("value", False):
            raise RuntimeError("injected")
        return 0

    second = journal.add(OperationStep("up", "vm", "vm-1", apply=flaky, depends_on=(first.key,)))
    assert not journal.run()
    assert second.state == OperationStepState.FAILED
    assert journal.run()
    assert calls == ["infra", "vm", "vm"]
    assert first.attempts == 1
    assert second.attempts == 2


def test_compensation_is_reverse_dependency_order_and_best_effort():
    calls = []
    journal = OperationJournal()
    first = journal.add(
        OperationStep(
            "infra",
            resource_type="infra",
            resource_id="global",
            apply=lambda: calls.append("apply-infra") or 0,
            compensate=lambda: calls.append("comp-infra") or 0,
        )
    )
    journal.add(
        OperationStep(
            "vm",
            resource_type="vm",
            resource_id="vm-1",
            apply=lambda: calls.append("apply-vm") or 0,
            compensate=lambda: calls.append("comp-vm") or 0,
            depends_on=(first.key,),
        )
    )
    assert journal.run()
    assert journal.compensate()
    assert calls == ["apply-infra", "apply-vm", "comp-vm", "comp-infra"]


def test_structured_failure_is_retained_in_step_and_journal():
    journal = OperationJournal(
        [OperationStep("container", "container", "c1", apply=lambda: 17)]
    )
    assert not journal.run()
    step = journal.steps[0]
    assert step.state == OperationStepState.FAILED
    assert step.result == 17
    assert step.error["resource_type"] == "container"
    assert step.error["resource_id"] == "c1"
    assert step.error["operation"] == "container"
    assert step.error["message"]
    assert json.dumps(journal.to_dict(), sort_keys=True)
