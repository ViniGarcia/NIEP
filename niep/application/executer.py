from niep.runtime.mininet_switch import start_switch
from niep.runtime.infrastructure import DEFAULT_INFRASTRUCTURE_RUNTIME
from niep.runtime.errors import cleanup_failure_record
from os import getenv
from types import SimpleNamespace
from niep.application.mininet_adapter import MininetApplyError, MininetTopologyAdapter
from niep.application.planner import TopologyPlanner, TopologyPlanningError
from niep.application.lifecycle import (
    OperationJournal,
    OperationStep,
    TopologyState,
    TopologyStateMachine,
    operation_key,
)

try:  # Mininet is installed by the integration image, not on host-only runs.
    from mininet.net import Mininet
    from mininet.node import Host
    from mininet.node import Switch
    from mininet.node import OVSSwitch
    from mininet.node import Controller, RemoteController
    from mininet.link import Link, Intf
    from mininet.clean import Cleanup
except ImportError:  # pragma: no cover - import-only fallback
    class _UnavailableMininet:
        def __init__(self, *_args, **_kwargs):
            raise RuntimeError("Mininet is unavailable; install the integration dependencies")

    Mininet = Host = Switch = OVSSwitch = Controller = RemoteController = Link = Intf = _UnavailableMininet

    class Cleanup:
        def cleanup(self):
            return None


class Executer:
    def __init__(self, CONFIGURATION, infrastructure=None, runtime_factory=None):
        self.CONFIGURATION = None
        self.HOSTS = {}
        self.SWITCHES = {}
        self.OVSSWITCHES = {}
        self.CONTROLLERS = {}
        self.VMS = {}
        self.VNFS = {}
        self.CONTAINERS = {}
        self.POX = None
        self.NET = None
        self.STATUS = None
        self.DETAIL = ""
        self.CLEANUP_ERRORS = []
        self.CLEANUP_REQUIRED = False
        self._CLEANUP_COMPLETED = set()
        self._PERSISTENT_STATE_COMPLETED = set()
        self.SWITCH_CONTROLLER_ID = None
        self.LOCAL_POX_ENABLED = True
        # Lifecycle state and startup progress belong to the application
        # orchestrator.  Runtime objects keep their historical flags/statuses
        # for compatibility at this boundary only.
        self._lifecycle = TopologyStateMachine(TopologyState.UNDEFINED)
        self.JOURNAL = OperationJournal()
        self.journal = self.JOURNAL
        if infrastructure is None and runtime_factory is not None:
            infrastructure = runtime_factory.infrastructure()
        self.INFRASTRUCTURE = infrastructure if infrastructure is not None else DEFAULT_INFRASTRUCTURE_RUNTIME

        if CONFIGURATION.STATUS == 0:
            self.CONFIGURATION = CONFIGURATION
            self._lifecycle.force(TopologyState.DEFINED)
            self.LOCAL_POX_ENABLED = getenv("NIEP_DISABLE_LOCAL_POX", "0").lower() not in ("1", "true", "yes")
        else:
            self.STATUS = -4

    @property
    def lifecycle_state(self):
        """Typed lifecycle state; numeric ``STATUS`` is a compatibility edge."""

        return self._lifecycle.state

    @property
    def state(self):
        return self._lifecycle.state

    def _lifecycle_transition(self, target, *, force=False):
        target = TopologyState(target)
        if force:
            return self._lifecycle.force(target)
        if self._lifecycle.state == target:
            return target
        return self._lifecycle.transition(target)

#------------------------------------------------------------------

    def interfacesMaping(self):
        return self.INFRASTRUCTURE.interfaces_mapping()

    def externalEndpoints(self):
        endpoints = {}
        for vm_id in self.VMS:
            endpoints[vm_id] = self.VMS[vm_id]
        for container_id in self.CONTAINERS:
            endpoints[container_id] = self.CONTAINERS[container_id]
        for vnf_id in self.VNFS:
            endpoints[vnf_id] = self.VNFS[vnf_id].VM
        return endpoints

#------------------------------------------------------------------

    def _mininet_plan(self):
        """Build a deterministic Mininet plan without applying it."""

        try:
            self._MININET_PLAN = TopologyPlanner(
                self.CONFIGURATION,
                interface_mapping=self.interfacesMaping(),
                external_endpoints=self.externalEndpoints(),
                local_pox_enabled=self.LOCAL_POX_ENABLED,
            ).plan()
        except TopologyPlanningError as exc:
            self.STATUS = exc.status
            self.DETAIL = exc.detail
            return exc.status
        return 0

    def _mininet_apply(self):
        """Apply the already planned Mininet topology."""

        try:
            plan = self._MININET_PLAN
            adapter = MininetTopologyAdapter(
                mininet_cls=Mininet,
                cleanup_cls=Cleanup,
                intf_cls=Intf,
                remote_controller_cls=RemoteController,
                local_pox=self.INFRASTRUCTURE.start_local_pox,
            )
            applied = adapter.apply(
                plan,
                runtime_configuration=self.CONFIGURATION,
                runtime_nodes={
                    "hosts": self._runtime_index(self.CONFIGURATION.MNHOSTS),
                    "switches": self._runtime_index(self.CONFIGURATION.MNSWITCHES),
                    "controllers": self._runtime_index(self.CONFIGURATION.MNCONTROLLER),
                    "ovs_switches": self._runtime_index(self.CONFIGURATION.MNOVSES),
                },
            )
        except MininetApplyError as exc:
            self._capture_mininet_topology(exc.partial, plan)
            self.STATUS = -10
            self.DETAIL = exc.message
            raise
        except TopologyPlanningError as exc:
            self.STATUS = exc.status
            self.DETAIL = exc.detail
            return exc.status
        self._capture_mininet_topology(applied, plan)
        self.STATUS = 0
        return 0

    def _capture_mininet_topology(self, applied, plan):
        """Publish complete or partial adapter handles before cleanup/retry."""

        self.NET = applied.net
        self.POX = applied.pox
        self.HOSTS = self._runtime_index(self.CONFIGURATION.MNHOSTS)
        self.SWITCHES = self._runtime_index(self.CONFIGURATION.MNSWITCHES)
        self.CONTROLLERS = self._runtime_index(self.CONFIGURATION.MNCONTROLLER)
        self.OVSSWITCHES = self._runtime_index(self.CONFIGURATION.MNOVSES)
        if "UNICTRL" in applied.controllers:
            self.CONTROLLERS["UNICTRL"] = SimpleNamespace(
                ID="UNICTRL", IP="127.0.0.1", PORT=6633,
                ELEM=applied.controllers["UNICTRL"],
            )
        self.SWITCH_CONTROLLER_ID = plan.switch_controller_id

    def mininetPrepare(self):
        """Compatibility entry point for plan+apply callers."""

        if self._mininet_plan() != 0:
            return self.STATUS
        return self._mininet_apply()

    @staticmethod
    def _runtime_index(values):
        return {
            getattr(value, "ID", getattr(value, "id", None)): value
            for value in (values or ())
            if getattr(value, "ID", getattr(value, "id", None)) is not None
        }

#------------------------------------------------------------------

    @staticmethod
    def _resource_detail(resource_type, resource_id, resource):
        """Preserve a legacy runtime's resource-scoped diagnostic detail."""

        if resource is None:
            return ""
        detail = getattr(resource, "DETAIL", "")
        if detail in (None, ""):
            return ""
        return f"{resource_type} {resource_id}: {detail}"

    def _stage_result(
        self,
        operation,
        resource_type,
        resource_id,
        callback,
        *,
        detail_source=None,
    ):
        """Call one legacy adapter operation at the lifecycle boundary."""

        try:
            result = callback()
        except Exception as exc:  # journal retains the structured exception
            self.DETAIL = self._resource_detail(
                resource_type, resource_id, detail_source
            ) or str(exc)
            self.STATUS = -10
            raise
        successful = (
            result is None
            or result is True
            or (isinstance(result, int) and not isinstance(result, bool) and result == 0)
        )
        if not successful:
            self.STATUS = (
                result
                if isinstance(result, int) and not isinstance(result, bool)
                else -10
            )
            self.DETAIL = (
                self._resource_detail(resource_type, resource_id, detail_source)
                or getattr(callback, "DETAIL", "")
                or str(result)
            )
        return result

    def _cleanup_callback(self, resource_type, resource_id, resource, method_name, key):
        fallback_names = {
            "vm": "downVM",
            "vnf": "downVNF",
            "container": "downContainer",
        }
        method = getattr(resource, method_name, None) or getattr(
            resource,
            fallback_names.get(resource_type, "down" + resource_type.title()),
        )

        def cleanup():
            result = self._stage_result(
                method_name,
                resource_type,
                resource_id,
                method,
                detail_source=resource,
            )
            self._CLEANUP_COMPLETED.add(key)
            return result

        return cleanup

    def _build_startup_journal(self):
        """Declare startup operations and their dependency-aware compensations."""

        if len(self.JOURNAL):
            return
        self.JOURNAL = OperationJournal()
        self.journal = self.JOURNAL
        last_steps = []

        def add(operation, resource_type, resource_id, callback, compensate=None, depends_on=()):
            step = OperationStep(
                operation,
                resource_type,
                resource_id,
                apply=callback,
                compensate=compensate,
                depends_on=tuple(depends_on),
            )
            self.JOURNAL.add(step)
            return step

        infra_key = operation_key("prepare", "infrastructure", "global")
        add(
            "prepare",
            "infrastructure",
            "global",
            lambda: self._stage_result(
                "prepare_topology_infrastructure",
                "infrastructure",
                "global",
                self.INFRASTRUCTURE.prepare_topology_infrastructure,
            ),
            compensate=lambda: self._stage_result(
                "cleanup_topology_infrastructure",
                "infrastructure",
                "global",
                self.INFRASTRUCTURE.cleanup_topology_infrastructure,
            ),
        )

        vm_up_steps = []
        for vm in self.CONFIGURATION.VMS:
            vm_id = vm.ID
            self.VMS[vm_id] = vm
            create = add(
                "create",
                "vm",
                vm_id,
                lambda vm=vm: self._vm_create(vm),
                depends_on=(infra_key,),
            )
            # Bind the step itself after ``add`` returns.  Binding the loop
            # variable in the call above would make every compensation refer
            # to the final VM/VNF create step in a multi-resource topology.
            create.compensate = lambda vm=vm, vm_id=vm_id, create=create: self._compensate_owned(
                create, "vm", vm_id, vm, "cleanupVM", ("vm", vm_id, "downVM")
            )
            apply = add(
                "apply",
                "vm",
                vm_id,
                lambda vm=vm, create=create: self._vm_apply(vm, create),
                depends_on=(create.key,),
            )
            up = add(
                "up",
                "vm",
                vm_id,
                lambda vm=vm: self._vm_up(vm),
                depends_on=(apply.key,),
            )
            vm_up_steps.append(up.key)
            last_steps.append(up.key)

        vnf_up_steps = []
        for vnf in self.CONFIGURATION.VNFS:
            vnf_id = vnf.ID
            self.VNFS[vnf_id] = vnf
            create = add(
                "create",
                "vnf",
                vnf_id,
                lambda vnf=vnf: self._vnf_create(vnf),
                depends_on=tuple(vm_up_steps or (infra_key,)),
            )
            create.compensate = lambda vnf=vnf, vnf_id=vnf_id, create=create: self._compensate_owned(
                create, "vnf", vnf_id, vnf, "cleanupVNF", ("vnf", vnf_id, "downVNF")
            )
            apply = add(
                "apply",
                "vnf",
                vnf_id,
                lambda vnf=vnf, create=create: self._vnf_apply(vnf, create),
                depends_on=(create.key,),
            )
            up = add(
                "up",
                "vnf",
                vnf_id,
                lambda vnf=vnf: self._vnf_up(vnf),
                depends_on=(apply.key,),
            )
            vnf_up_steps.append(up.key)
            last_steps.append(up.key)

        for container in self.CONFIGURATION.CONTAINERS:
            container_id = container.ID
            self.CONTAINERS[container_id] = container
            add(
                "up",
                "container",
                container_id,
                lambda container=container: self._container_up(container),
                compensate=self._cleanup_callback(
                    "container",
                    container_id,
                    container,
                    "cleanupContainer",
                    ("container", container_id, "downContainer"),
                ),
                depends_on=tuple(vnf_up_steps or vm_up_steps or (infra_key,)),
            )
            last_steps.append(operation_key("up", "container", container_id))

        for index, sfc in enumerate(self.CONFIGURATION.SFCS):
            sfc_id = getattr(sfc, "ID", index)
            prepare = getattr(sfc, "prepareSFC", None)
            if getattr(sfc, "SFC_VNFS_CONF", None) or not callable(prepare):
                def prepare():
                    return None
            add(
                "prepare",
                "sfc",
                f"{sfc_id}:{index}",
            lambda prepare=prepare, sfc_id=sfc_id, sfc=sfc: self._stage_result(
                "prepareSFC",
                "sfc",
                sfc_id,
                prepare,
                detail_source=sfc,
            ),
                compensate=lambda sfc=sfc, index=index: self._compensate_sfc(sfc, index),
                depends_on=tuple(vnf_up_steps or vm_up_steps or (infra_key,)),
            )
            last_steps.append(operation_key("prepare", "sfc", f"{sfc_id}:{index}"))

        plan = add(
            "plan",
            "mininet",
            getattr(self.CONFIGURATION, "ID", "topology"),
            self._mininet_plan,
            depends_on=tuple(last_steps or (infra_key,)),
        )
        applied = add(
            "apply",
            "mininet",
            getattr(self.CONFIGURATION, "ID", "topology"),
            self._mininet_apply,
            compensate=self._compensate_mininet,
            depends_on=(plan.key,),
        )

        controller_steps = {}
        runtime_controllers = self._runtime_index(self.CONFIGURATION.MNCONTROLLER)
        runtime_switches = self._runtime_index(self.CONFIGURATION.MNSWITCHES)
        for controller_id, controller in runtime_controllers.items():
            controller_step = add(
                "up",
                "controller",
                controller_id,
                lambda controller=controller, controller_id=controller_id: self._stage_result("controller.start", "controller", controller_id, controller.ELEM.start),
                compensate=lambda controller=controller, controller_id=controller_id: self._compensate_element(controller, "controller", controller_id),
                depends_on=(applied.key,),
            )
            controller_steps[controller_id] = controller_step.key
        runtime_ovs = self._runtime_index(self.CONFIGURATION.MNOVSES)
        # The planner synthesizes UNICTRL for regular switches even when
        # remote controllers are also configured.  Keep that local controller
        # as an explicit startup step so every controller returned by the
        # Mininet adapter is started and the switch dependency is accurate.
        if self.LOCAL_POX_ENABLED and runtime_switches:
            implicit_controller = add(
                "up",
                "controller",
                "UNICTRL",
                lambda: self._start_runtime_controller("UNICTRL"),
                compensate=lambda: self._compensate_runtime_element(
                    "UNICTRL", "controller"
                ),
                depends_on=(applied.key,),
            )
            controller_steps["UNICTRL"] = implicit_controller.key
        for switch_id, switch in runtime_ovs.items():
            controller_dependency = controller_steps.get(getattr(switch, "CONTROLLER", None))
            dependencies = (applied.key,) + ((controller_dependency,) if controller_dependency else ())
            add(
                "up",
                "ovs_switch",
                switch_id,
                lambda switch=switch, switch_id=switch_id: self._stage_result(
                    "ovs.start", "ovs_switch", switch_id,
                    lambda: start_switch(switch.ELEM, [self.CONTROLLERS[switch.CONTROLLER].ELEM]),
                ),
                compensate=lambda switch=switch, switch_id=switch_id: self._compensate_element(switch, "ovs_switch", switch_id),
                depends_on=dependencies,
            )
        for switch_id, switch in runtime_switches.items():
            default_controller = self.SWITCH_CONTROLLER_ID or (
                "UNICTRL" if "UNICTRL" in controller_steps else next(iter(controller_steps), None)
            )
            controller_dependency = controller_steps.get(default_controller)
            dependencies = (applied.key,) + ((controller_dependency,) if controller_dependency else ())
            add(
                "up",
                "switch",
                switch_id,
                lambda switch=switch: self._start_switch(switch),
                compensate=lambda switch=switch, switch_id=switch_id: self._compensate_element(switch, "switch", switch_id),
                depends_on=dependencies,
            )

    def _vm_create(self, vm):
        result = vm.createVM()
        step = self.JOURNAL.get(operation_key("create", "vm", vm.ID))
        if result in (-1, -2):
            if step:
                step.metadata["needs_apply"] = result == -1
                # Both legacy outcomes entered the transaction and the
                # cleanup methods are idempotent.  ``-1`` additionally means
                # apply may allocate partially, so ownership is recorded
                # before that follow-up step is entered.  Keeping ``-2``
                # compensable preserves the established teardown ledger for
                # already-present compute resources.
                step.metadata["owned"] = True
            return 0
        if step:
            step.metadata["needs_apply"] = False
            step.metadata["owned"] = True
        return self._stage_result(
            "createVM", "vm", vm.ID, lambda: result, detail_source=vm
        )

    def _vm_apply(self, vm, create):
        apply = self.JOURNAL.get(operation_key("apply", "vm", vm.ID))
        if not create.metadata.get("needs_apply"):
            if apply:
                apply.mark_skipped("included in createVM")
            return 0
        # Establish ownership before invoking an adapter that may fail after
        # allocating only part of the resource.
        create.metadata["owned"] = True
        return self._stage_result(
            "applyVM", "vm", vm.ID, vm.applyVM, detail_source=vm
        )

    def _vm_up(self, vm):
        result = vm.upVM()
        if result is None:
            result = getattr(vm, "VM_STATUS", None)
        return self._stage_result(
            "upVM", "vm", vm.ID, lambda: result, detail_source=vm
        )

    def _vnf_create(self, vnf):
        result = vnf.createVNF()
        step = self.JOURNAL.get(operation_key("create", "vnf", vnf.ID))
        if result in (-1, -2):
            if step:
                step.metadata["needs_apply"] = result == -1
                step.metadata["owned"] = True
            return 0
        if step:
            step.metadata["needs_apply"] = False
            step.metadata["owned"] = True
        return self._stage_result(
            "createVNF", "vnf", vnf.ID, lambda: result, detail_source=vnf
        )

    def _vnf_apply(self, vnf, create):
        apply = self.JOURNAL.get(operation_key("apply", "vnf", vnf.ID))
        if not create.metadata.get("needs_apply"):
            if apply:
                apply.mark_skipped("included in createVNF")
            return 0
        create.metadata["owned"] = True
        method = getattr(vnf, "applyVNF", None)
        if method is None:
            method = getattr(vnf.VM, "applyVM")
        return self._stage_result(
            "applyVNF", "vnf", vnf.ID, method, detail_source=vnf
        )

    def _vnf_up(self, vnf):
        result = vnf.upVNF()
        if result is None:
            result = getattr(vnf, "VNF_STATUS", None)
        return self._stage_result(
            "upVNF", "vnf", vnf.ID, lambda: result, detail_source=vnf
        )

    def _container_up(self, container):
        result = container.upContainer()
        if result is None:
            result = getattr(container, "CONTAINER_STATUS", None)
        return self._stage_result(
            "upContainer",
            "container",
            container.ID,
            lambda: result,
            detail_source=container,
        )

    def _compensate_owned(self, step, resource_type, resource_id, resource, method_name, key):
        if step.metadata.get("owned") is False:
            return 0
        return self._cleanup_callback(resource_type, resource_id, resource, method_name, key)()

    def _start_switch(self, switch):
        if self.SWITCH_CONTROLLER_ID not in self.CONTROLLERS:
            return self._stage_result("switch.start", "switch", switch.ID, lambda: -4)
        return self._stage_result(
            "switch.start",
            "switch",
            switch.ID,
            lambda: start_switch(switch.ELEM, [self.CONTROLLERS[self.SWITCH_CONTROLLER_ID].ELEM]),
        )

    def _start_runtime_controller(self, controller_id):
        controller = self.CONTROLLERS.get(controller_id)
        if controller is None:
            return self._stage_result("controller.start", "controller", controller_id, lambda: -4)
        return self._stage_result(
            "controller.start",
            "controller",
            controller_id,
            controller.ELEM.start,
        )

    def _compensate_runtime_element(self, element_id, resource_type):
        element = self.CONTROLLERS.get(element_id) if resource_type == "controller" else None
        if element is None:
            return 0
        return self._compensate_element(element, resource_type, element_id)

    def _compensate_element(self, element, resource_type, resource_id):
        result = self._stage_result("stop", resource_type, resource_id, element.ELEM.stop)
        self._CLEANUP_COMPLETED.add((resource_type, resource_id, "stop"))
        return result

    def _compensate_mininet(self):
        def successful(value):
            return (
                value is None
                or value is True
                or (isinstance(value, int) and not isinstance(value, bool) and value == 0)
            )

        failures = []
        if self.NET is not None:
            try:
                result = self._stage_result("stop", "mininet", "topology", self.NET.stop)
                if not successful(result):
                    failures.append(RuntimeError("mininet stop returned " + str(result)))
                else:
                    self._CLEANUP_COMPLETED.add(("mininet", "topology", "stop"))
            except Exception as exc:  # best effort: POX must still be attempted
                failures.append(exc)
        else:
            result = 0
        if self.POX is not None:
            try:
                pox_result = self._stage_result(
                    "stop_process",
                    "process",
                    "pox",
                    lambda: self.INFRASTRUCTURE.stop_process(self.POX),
                )
                if not successful(pox_result):
                    failures.append(RuntimeError("pox stop returned " + str(pox_result)))
                else:
                    self._CLEANUP_COMPLETED.add(("process", "pox", "stop_process"))
            except Exception as exc:  # best effort
                failures.append(exc)
        if failures:
            raise RuntimeError("mininet compensation failed: " + " | ".join(str(error) for error in failures)) from failures[0]
        return result

    def _compensate_sfc(self, sfc, index):
        sfc.SFC_UP = False
        self._CLEANUP_COMPLETED.add(("sfc", getattr(sfc, "ID", "unknown"), index, "mark_down"))
        return 0

    def _rollback_journal(self):
        if not len(self.JOURNAL):
            return []
        self.JOURNAL.compensate(best_effort=True)
        errors = [
            step.compensation_error
            for step in self.JOURNAL
            if step.compensation_error is not None
        ]
        errors = [error for error in errors if error]
        self.CLEANUP_ERRORS = errors
        self.CLEANUP_REQUIRED = bool(errors)
        if errors and self.lifecycle_state in {
            TopologyState.STARTING,
            TopologyState.FAILED,
            TopologyState.STOPPING,
        }:
            self._lifecycle_transition(TopologyState.CLEANUP_PENDING)
        return errors

    def topologyUp(self):
        if self.lifecycle_state == TopologyState.UP:
            return 0
        if self.lifecycle_state == TopologyState.CLEANUP_PENDING:
            # A pending compensation must be retried through down/clean before
            # a new startup transaction can be admitted.
            self.STATUS = -10
            return -10
        if self.lifecycle_state not in {
            TopologyState.DEFINED,
            TopologyState.DOWN,
            TopologyState.FAILED,
        }:
            # Do not build a journal or invoke an adapter while an operation is
            # already in flight, the topology is undefined, or it was
            # destroyed.  Numeric status remains only this compatibility-edge
            # response; lifecycle decisions use the typed state above.
            self.STATUS = -10
            return -10
        if self.lifecycle_state in {TopologyState.DEFINED, TopologyState.DOWN, TopologyState.FAILED}:
            self._lifecycle_transition(TopologyState.STARTING)
        self.CLEANUP_ERRORS = []
        self.CLEANUP_REQUIRED = True
        self._CLEANUP_COMPLETED = set()
        self._PERSISTENT_STATE_COMPLETED = set()
        self.DETAIL = ""
        self._build_startup_journal()
        if not self.JOURNAL.run():
            self._lifecycle_transition(TopologyState.FAILED)
            self.STATUS = self.STATUS if isinstance(self.STATUS, int) and self.STATUS != 0 else -10
            return self.STATUS
        self.STATUS = 0
        # A successful startup owns active resources and therefore still needs
        # the legacy teardown ledger for down/clean/destroy.  The operation
        # journal tracks startup progress; it does not replace that ledger.
        self.CLEANUP_REQUIRED = True
        self._lifecycle_transition(TopologyState.UP)
        return 0

#------------------------------------------------------------------

    def topologyDown(self):
        if self.lifecycle_state in {
            TopologyState.UNDEFINED,
            TopologyState.DESTROYED,
            TopologyState.STARTING,
            TopologyState.STOPPING,
        }:
            # A down command is idempotent only for already-down/defined
            # topologies.  Reject an in-flight or non-materialized operation
            # before consulting any runtime callback.
            self.STATUS = -10
            return -10
        if self.lifecycle_state == TopologyState.DOWN and not self.CLEANUP_REQUIRED:
            self.STATUS = None
            self.DETAIL = ""
            return 0
        if self.lifecycle_state == TopologyState.DEFINED and not self.CLEANUP_REQUIRED and not self.JOURNAL.incomplete:
            self._lifecycle_transition(TopologyState.DOWN)
            self.STATUS = None
            self.DETAIL = ""
            return 0
        # Legacy callers may construct an executor directly and set STATUS=0;
        # reconcile that one boundary observation into the typed state.
        if self.lifecycle_state == TopologyState.DEFINED and self.CLEANUP_REQUIRED:
            self._lifecycle_transition(TopologyState.UP, force=True)
        if self.lifecycle_state == TopologyState.UP:
            self._lifecycle_transition(TopologyState.STOPPING)
        if len(self.JOURNAL) and any(step.complete or step.attempted for step in self.JOURNAL):
            cleanupErrors = self._cleanupJournal()
        else:
            cleanupErrors = self._cleanupResources()

        if cleanupErrors:
            self.STATUS = -10
            self.DETAIL = self._cleanupDetail(cleanupErrors)
            if self.lifecycle_state in {TopologyState.STOPPING, TopologyState.FAILED}:
                self._lifecycle_transition(TopologyState.CLEANUP_PENDING)
            return -10

        self.STATUS = None
        self.DETAIL = ""
        if self.lifecycle_state in {
            TopologyState.STOPPING,
            TopologyState.CLEANUP_PENDING,
            TopologyState.FAILED,
            TopologyState.DEFINED,
        }:
            self._lifecycle_transition(TopologyState.DOWN)
        return 0

#------------------------------------------------------------------

    def rollbackFailedStart(self):
        startupDetail = self.DETAIL
        if len(self.JOURNAL):
            cleanupErrors = self._rollback_journal()
        else:
            cleanupErrors = self._cleanupResources()

        if cleanupErrors:
            self.STATUS = -10
            suffix = "Rollback warnings: " + self._cleanupDetail(cleanupErrors)
            self.DETAIL = (self.DETAIL + " | " if self.DETAIL else "") + suffix
            if self.lifecycle_state in {
                TopologyState.STARTING,
                TopologyState.FAILED,
                TopologyState.STOPPING,
            }:
                self._lifecycle_transition(TopologyState.CLEANUP_PENDING)
        else:
            self.DETAIL = startupDetail
            if self.lifecycle_state == TopologyState.STARTING:
                self._lifecycle_transition(TopologyState.FAILED)
        return cleanupErrors

    def _cleanupJournal(self):
        """Compensate a declared startup plan in reverse dependency order."""

        self.JOURNAL.compensate(best_effort=True)
        cleanupErrors = [
            step.compensation_error
            for step in self.JOURNAL
            if step.compensation_error is not None
        ]
        self.CLEANUP_ERRORS = [error for error in cleanupErrors if error]
        self.CLEANUP_REQUIRED = bool(self.CLEANUP_ERRORS)
        return self.CLEANUP_ERRORS

    def _cleanupResources(self):
        if not self.CLEANUP_REQUIRED:
            self.CLEANUP_ERRORS = []
            return []

        cleanupErrors = []

        if self.NET is not None:
            self._attemptCleanup(
                cleanupErrors,
                ("mininet", "topology", "stop"),
                "mininet",
                getattr(self.CONFIGURATION, "ID", "topology"),
                "stop",
                self.NET.stop,
            )

        self._cleanupMininetElements(cleanupErrors, self.OVSSWITCHES, "ovs_switch")
        self._cleanupMininetElements(cleanupErrors, self.CONTROLLERS, "controller")
        self._cleanupMininetElements(cleanupErrors, self.SWITCHES, "switch")

        if self.POX is not None:
            self._attemptCleanup(
                cleanupErrors,
                ("process", "pox", "stop_process"),
                "process",
                "pox",
                "stop_process",
                lambda: self.INFRASTRUCTURE.stop_process(self.POX),
            )

        self._attemptCleanup(
            cleanupErrors,
            ("infrastructure", "global", "cleanup_topology_infrastructure"),
            "infrastructure",
            "global",
            "cleanup_topology_infrastructure",
            self.INFRASTRUCTURE.cleanup_topology_infrastructure,
            self.INFRASTRUCTURE,
        )

        for containerID, container in list(self.CONTAINERS.items()):
            cleanup = getattr(container, "cleanupContainer", None) or container.downContainer
            self._attemptCleanup(
                cleanupErrors,
                ("container", containerID, "downContainer"),
                "container",
                containerID,
                "downContainer",
                cleanup,
                container,
            )

        for vnfID, vnf in list(self.VNFS.items()):
            cleanup = getattr(vnf, "cleanupVNF", None) or vnf.downVNF
            self._attemptCleanup(
                cleanupErrors,
                ("vnf", vnfID, "downVNF"),
                "vnf",
                vnfID,
                "downVNF",
                cleanup,
                vnf,
            )

        for vmID, vm in list(self.VMS.items()):
            cleanup = getattr(vm, "cleanupVM", None) or vm.downVM
            self._attemptCleanup(
                cleanupErrors,
                ("vm", vmID, "downVM"),
                "vm",
                vmID,
                "downVM",
                cleanup,
                vm,
            )

        for sfcIndex, sfc in enumerate(list(getattr(self.CONFIGURATION, "SFCS", []))):
            sfcID = getattr(sfc, "ID", "unknown")
            self._attemptCleanup(
                cleanupErrors,
                # SFC ids are not used as dictionary keys.  Include the
                # position as a stable discriminator so two SFC objects with
                # the same (legacy) id cannot make one another look cleaned.
                ("sfc", sfcID, sfcIndex, "mark_down"),
                "sfc",
                sfcID,
                "mark_down",
                lambda sfc=sfc: setattr(sfc, "SFC_UP", False),
            )

        self.CLEANUP_ERRORS = cleanupErrors
        self.CLEANUP_REQUIRED = bool(cleanupErrors)
        return cleanupErrors

    def _cleanupMininetElements(self, cleanupErrors, elements, resourceType):
        for elementID, element in list(elements.items()):
            mininetElement = getattr(element, "ELEM", None)
            if mininetElement is None:
                continue
            self._attemptCleanup(
                cleanupErrors,
                (resourceType, elementID, "stop"),
                resourceType,
                elementID,
                "stop",
                mininetElement.stop,
            )

    def _attemptCleanup(
        self,
        cleanupErrors,
        cleanupKey,
        resourceType,
        resourceID,
        operation,
        cleanup,
        resource=None,
    ):
        if cleanupKey in self._CLEANUP_COMPLETED:
            return

        try:
            status = cleanup()
        except Exception as exc:
            nestedErrors = getattr(resource, "CLEANUP_ERRORS", None)
            if nestedErrors:
                cleanupErrors.extend(self._structuredCleanupErrors(nestedErrors))
            cleanupErrors.append(
                cleanup_failure_record(
                    exc,
                    resource_type=resourceType,
                    resource_id=resourceID,
                    operation=operation,
                )
            )
            return

        if status not in (0, None):
            nestedErrors = getattr(resource, "CLEANUP_ERRORS", None)
            if nestedErrors:
                cleanupErrors.extend(self._structuredCleanupErrors(nestedErrors))
            else:
                message = getattr(resource, "DETAIL", "") or str(status)
                cleanupErrors.append(
                    self._cleanupError(resourceType, resourceID, operation, message)
                )
            return

        self._CLEANUP_COMPLETED.add(cleanupKey)

    def _structuredCleanupErrors(self, errors):
        """Return cleanup errors as serializable, structured records.

        Runtime adapters written before the teardown contract sometimes expose
        plain strings.  Keep their details while assigning the parent resource
        context; modern adapters already return dictionaries and are copied
        unchanged.  This also prevents a malformed adapter error from making
        the whole teardown reporting path fail.
        """
        structured = []
        if errors is None:
            return structured
        if isinstance(errors, (dict, str, bytes)) or not hasattr(errors, "__iter__"):
            errors = [errors]
        for error in errors:
            structured.append(
                cleanup_failure_record(
                    error,
                    resource_type="unknown",
                    resource_id="unknown",
                    operation="cleanup",
                )
            )
        return structured

    def _cleanupError(self, resourceType, resourceID, operation, message):
        return {
            "resource_type": str(resourceType),
            "resource_id": str(resourceID),
            "operation": str(operation),
            "message": str(message),
            "cause": None,
            "context": {},
            "retryable": False,
        }

    def _cleanupDetail(self, cleanupErrors):
        return " | ".join(
            error["resource_type"]
            + " "
            + error["resource_id"]
            + " "
            + error["operation"]
            + " failed: "
            + error["message"]
            for error in cleanupErrors
        )

#------------------------------------------------------------------
