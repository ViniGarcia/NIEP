from types import SimpleNamespace

import pytest

from niep.application.executer import Executer
from niep.application.lifecycle import OperationStepState, TopologyState, operation_key


class Resource:
    def __init__(self, resource_id):
        self.ID = resource_id
        self.VM_STATUS = 0
        self.VNF_STATUS = 0
        self.CONTAINER_STATUS = 0
        self.SFC_UP = False
        self.calls = []
        self.create_vm_result = 0
        self.apply_vm_result = 0
        self.create_vnf_result = 0
        self.apply_vnf_result = 0

    def createVM(self):
        self.calls.append("create")
        return self.create_vm_result

    def applyVM(self):
        self.calls.append("apply")
        return self.apply_vm_result

    def upVM(self):
        self.calls.append("up")
        return 0

    def cleanupVM(self):
        self.calls.append("cleanup")
        return 0

    def createVNF(self):
        self.calls.append("create")
        return self.create_vnf_result

    def applyVNF(self):
        self.calls.append("apply")
        return self.apply_vnf_result

    def upVNF(self):
        self.calls.append("up")
        return 0

    def cleanupVNF(self):
        self.calls.append("cleanup")
        return 0

    def upContainer(self):
        self.calls.append("up")
        return 0

    def cleanupContainer(self):
        self.calls.append("cleanup")
        return 0

    def prepareSFC(self):
        self.calls.append("prepare")
        return 0


class Infrastructure:
    def prepare_topology_infrastructure(self):
        return 0

    def cleanup_topology_infrastructure(self):
        return 0


class Element:
    def __init__(self, resource_id):
        self.ID = resource_id
        self.CONTROLLER = "c1"
        self.ELEM = self
        self.calls = []

    def start(self, *_args):
        self.calls.append("start")
        return 0

    def stop(self):
        self.calls.append("stop")
        return 0


def build_executor():
    vm = Resource("vm1")
    vnf = Resource("vnf1")
    container = Resource("container1")
    sfc = Resource("sfc1")
    controller = Element("c1")
    local_controller = Element("UNICTRL")
    ovs = Element("ovs1")
    switch = Element("s1")
    configuration = SimpleNamespace(
        STATUS=0,
        ID="journal-topology",
        VMS=[vm],
        VNFS=[vnf],
        CONTAINERS=[container],
        SFCS=[sfc],
        MNHOSTS=[],
        MNSWITCHES=[switch],
        MNCONTROLLER=[controller],
        MNOVSES=[ovs],
    )
    executor = Executer(configuration, infrastructure=Infrastructure())
    # Keep the baseline matrix focused on configured-controller startup.  The
    # dedicated local+remote contract below enables local POX explicitly.
    executor.LOCAL_POX_ENABLED = False

    def plan():
        return 0

    def apply():
        executor.CONTROLLERS = {"c1": controller, "UNICTRL": local_controller}
        executor.OVSSWITCHES = {"ovs1": ovs}
        executor.SWITCHES = {"s1": switch}
        executor.SWITCH_CONTROLLER_ID = "c1"
        return 0

    executor._mininet_plan = plan
    executor._mininet_apply = apply
    return executor, (vm, vnf, container, sfc, controller, ovs, switch, local_controller)


def stage_keys(executor):
    executor._build_startup_journal()
    return [step.key for step in executor.JOURNAL]


EXPECTED_STAGES = (
    operation_key("prepare", "infrastructure", "global"),
    operation_key("create", "vm", "vm1"),
    operation_key("apply", "vm", "vm1"),
    operation_key("up", "vm", "vm1"),
    operation_key("create", "vnf", "vnf1"),
    operation_key("apply", "vnf", "vnf1"),
    operation_key("up", "vnf", "vnf1"),
    operation_key("up", "container", "container1"),
    operation_key("prepare", "sfc", "sfc1:0"),
    operation_key("plan", "mininet", "journal-topology"),
    operation_key("apply", "mininet", "journal-topology"),
    operation_key("up", "controller", "c1"),
    operation_key("up", "ovs_switch", "ovs1"),
    operation_key("up", "switch", "s1"),
)


def test_real_startup_plan_declares_all_deterministic_stages():
    executor, _ = build_executor()
    assert stage_keys(executor) == list(EXPECTED_STAGES)


def test_local_pox_controller_is_started_alongside_configured_remote_controller():
    executor, resources = build_executor()
    executor.LOCAL_POX_ENABLED = True
    executor._build_startup_journal()

    local_key = operation_key("up", "controller", "UNICTRL")
    remote_key = operation_key("up", "controller", "c1")
    local = executor.JOURNAL.require(local_key)
    assert executor.JOURNAL.require(remote_key).depends_on == (
        operation_key("apply", "mininet", "journal-topology"),
    )
    assert local.depends_on == (operation_key("apply", "mininet", "journal-topology"),)
    ovs = executor.JOURNAL.require(operation_key("up", "ovs_switch", "ovs1"))
    switch = executor.JOURNAL.require(operation_key("up", "switch", "s1"))
    assert remote_key in ovs.depends_on
    assert local_key in switch.depends_on

    assert executor.topologyUp() == 0
    assert resources[4].calls == ["start"]
    assert resources[-1].calls == ["start"]


@pytest.mark.parametrize(
    "state",
    (
        TopologyState.UNDEFINED,
        TopologyState.STARTING,
        TopologyState.STOPPING,
        TopologyState.DESTROYED,
    ),
)
def test_up_rejects_non_admissible_states_before_building_journal(state):
    executor, _ = build_executor()
    executor._lifecycle.force(state)
    executor.INFRASTRUCTURE.prepare_topology_infrastructure = lambda: pytest.fail(
        "startup callback ran for an invalid state"
    )

    assert executor.topologyUp() == -10
    assert len(executor.JOURNAL) == 0


def test_failed_container_status_preserves_resource_detail_at_service_boundary():
    executor, resources = build_executor()
    container = resources[2]
    container.ID = "invalid-image-test"
    container.DETAIL = "invalid image reference"
    container.upContainer = lambda: -10
    executor._build_startup_journal()

    assert executor.topologyUp() == -10
    assert "invalid-image-test" in executor.DETAIL
    assert "invalid image reference" in executor.DETAIL
    assert executor.rollbackFailedStart() == []


@pytest.mark.parametrize(
    "state",
    (
        TopologyState.UNDEFINED,
        TopologyState.STARTING,
        TopologyState.STOPPING,
        TopologyState.DESTROYED,
    ),
)
def test_down_rejects_non_admissible_states_before_cleanup_callbacks(state):
    executor, _ = build_executor()
    executor._lifecycle.force(state)
    executor.CLEANUP_REQUIRED = True
    executor._cleanupResources = lambda: pytest.fail("cleanup callback ran for invalid state")

    assert executor.topologyDown() == -10


@pytest.mark.parametrize("failed_key", EXPECTED_STAGES)
def test_injected_failure_in_each_real_stage_is_deterministic(failed_key):
    executor, _ = build_executor()
    executor._build_startup_journal()
    failed = executor.JOURNAL.require(failed_key)
    failed.apply = lambda: (_ for _ in ()).throw(RuntimeError("injected-" + failed_key))

    result = executor.topologyUp()

    assert result != 0
    assert executor.state is TopologyState.FAILED
    assert failed.state is OperationStepState.FAILED
    assert failed.error["resource_type"]
    assert failed.error["resource_id"]
    assert failed.error["operation"]
    # Only the failed step and steps after it remain incomplete; completed
    # dependencies are available for a retry and are not re-run.
    assert failed.key in [step.key for step in executor.JOURNAL.incomplete]


def test_retry_runs_only_failed_and_following_steps():
    executor, resources = build_executor()
    executor._build_startup_journal()
    failed = executor.JOURNAL.require(operation_key("up", "vnf", "vnf1"))
    attempts = {"count": 0}

    def flaky():
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("injected")
        return 0

    failed.apply = flaky
    assert executor.topologyUp() != 0
    completed_before_retry = {
        step.key: step.attempts for step in executor.JOURNAL.completed
    }
    assert executor.topologyUp() == 0
    assert executor.state is TopologyState.UP
    assert failed.attempts == 2
    assert all(
        step.attempts == attempts_before
        for step in executor.JOURNAL.completed
        for key, attempts_before in completed_before_retry.items()
        if step.key == key
    )
    assert resources[0].calls == ["create", "up"]


@pytest.mark.parametrize(
    "failed_key",
    (
        EXPECTED_STAGES[0],  # infrastructure prepare
        EXPECTED_STAGES[3],  # VM up
        EXPECTED_STAGES[6],  # VNF up
        EXPECTED_STAGES[7],  # container up
        EXPECTED_STAGES[10],  # Mininet apply
        EXPECTED_STAGES[11],  # controller
        EXPECTED_STAGES[12],  # OVS
        EXPECTED_STAGES[13],  # switch
    ),
)
def test_partial_failure_compensates_the_failed_step_and_dependencies(failed_key):
    executor, resources = build_executor()
    executor._build_startup_journal()
    failed = executor.JOURNAL.require(failed_key)
    failed.apply = lambda: (_ for _ in ()).throw(RuntimeError("partial"))

    assert executor.topologyUp() != 0
    errors = executor.rollbackFailedStart()

    assert errors == []
    assert not executor.CLEANUP_REQUIRED
    assert failed.state is OperationStepState.COMPENSATED or failed.compensate is None
    # VM/VNF/container compensations are observable and must run even when
    # their own apply step raised after partially allocating a resource.
    if failed_key == EXPECTED_STAGES[3]:
        assert "cleanup" in resources[0].calls
    if failed_key == EXPECTED_STAGES[6]:
        assert "cleanup" in resources[1].calls
    if failed_key == EXPECTED_STAGES[7]:
        assert "cleanup" in resources[2].calls


@pytest.mark.parametrize(
    "failed_key,resource_index",
    (
        (EXPECTED_STAGES[1], 0),  # VM create
        (EXPECTED_STAGES[2], 0),  # VM apply
        (EXPECTED_STAGES[4], 1),  # VNF create
        (EXPECTED_STAGES[5], 1),  # VNF apply
    ),
)
def test_create_and_apply_failures_cleanup_owned_compute(failed_key, resource_index):
    executor, resources = build_executor()
    executor._build_startup_journal()
    failed = executor.JOURNAL.require(failed_key)
    failed.apply = lambda: (_ for _ in ()).throw(RuntimeError("partial-compute"))

    assert executor.topologyUp() != 0
    assert executor.rollbackFailedStart() == []
    assert "cleanup" in resources[resource_index].calls


def test_compute_compensation_binds_each_create_step_in_multi_resource_topology():
    executor, resources = build_executor()
    vm2 = Resource("vm2")
    vnf2 = Resource("vnf2")
    # The final VNF is an existing legacy resource.  If compensation closes
    # over the loop's final ``create`` variable, it incorrectly makes every
    # preceding VM/VNF use the wrong ownership record.  All resources entered
    # the transaction and their cleanup operations are idempotent.
    vnf2.create_vnf_result = -2
    executor.CONFIGURATION.VMS.append(vm2)
    executor.CONFIGURATION.VNFS.append(vnf2)
    executor._build_startup_journal()
    failed = executor.JOURNAL.require(EXPECTED_STAGES[-1])
    failed.apply = lambda: (_ for _ in ()).throw(RuntimeError("later-stage"))

    assert executor.topologyUp() != 0
    assert executor.rollbackFailedStart() == []
    assert "cleanup" in resources[0].calls
    assert "cleanup" in vm2.calls
    assert "cleanup" in resources[1].calls
    assert "cleanup" in vnf2.calls


@pytest.mark.parametrize(
    "resource_attr,apply_key,resource_index",
    (
        ("create_vm_result", EXPECTED_STAGES[2], 0),
        ("create_vnf_result", EXPECTED_STAGES[5], 1),
    ),
)
def test_create_minus_one_marks_ownership_before_partial_apply_failure(
    resource_attr, apply_key, resource_index
):
    executor, resources = build_executor()
    resource = resources[resource_index]
    setattr(resource, resource_attr, -1)
    if resource_index == 0:
        resource.apply_vm_result = -5
    else:
        resource.apply_vnf_result = -5
    executor._build_startup_journal()

    assert executor.topologyUp() != 0
    assert executor.JOURNAL.require(apply_key).state is OperationStepState.FAILED
    assert executor.rollbackFailedStart() == []
    assert "cleanup" in resource.calls


def test_normal_down_uses_declared_reverse_dependency_cleanup_order():
    executor, resources = build_executor()
    assert executor.topologyUp() == 0
    for resource in resources:
        resource.calls.clear()
    assert executor.topologyDown() == 0
    # The reverse plan reaches child resources before their VM/VNF parents.
    assert resources[2].calls == ["cleanup"]
    assert resources[1].calls == ["cleanup"]
    assert resources[0].calls == ["cleanup"]
    assert not executor.CLEANUP_REQUIRED


def test_mininet_compensation_attempts_pox_even_when_net_stop_fails():
    executor, _ = build_executor()
    calls = []

    class Net:
        def stop(self):
            calls.append("net")
            raise RuntimeError("net-busy")

    executor.NET = Net()
    executor.POX = object()

    def stop_process(_process):
        calls.append("pox")
        return 0

    executor.INFRASTRUCTURE.stop_process = stop_process

    with pytest.raises(RuntimeError):
        executor._compensate_mininet()
    assert calls == ["net", "pox"]
