from niep.runtime.infrastructure import DEFAULT_INFRASTRUCTURE_RUNTIME
from niep.runtime.errors import cleanup_failure_record
from os import getenv
from types import SimpleNamespace
from niep.application.mininet_adapter import MininetTopologyAdapter
from niep.application.planner import TopologyPlanner, TopologyPlanningError

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
        if infrastructure is None and runtime_factory is not None:
            infrastructure = runtime_factory.infrastructure()
        self.INFRASTRUCTURE = infrastructure if infrastructure is not None else DEFAULT_INFRASTRUCTURE_RUNTIME

        if CONFIGURATION.STATUS == 0:
            self.CONFIGURATION = CONFIGURATION
            self.LOCAL_POX_ENABLED = getenv("NIEP_DISABLE_LOCAL_POX", "0").lower() not in ("1", "true", "yes")
        else:
            self.STATUS = -4

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

    def mininetPrepare(self):
        try:
            plan = TopologyPlanner(
                self.CONFIGURATION,
                interface_mapping=self.interfacesMaping(),
                external_endpoints=self.externalEndpoints(),
                local_pox_enabled=self.LOCAL_POX_ENABLED,
            ).plan()
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
        except TopologyPlanningError as exc:
            self.STATUS = exc.status
            self.DETAIL = exc.detail
            return exc.status
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
        self.STATUS = 0
        return 0

    @staticmethod
    def _runtime_index(values):
        return {
            getattr(value, "ID", getattr(value, "id", None)): value
            for value in (values or ())
            if getattr(value, "ID", getattr(value, "id", None)) is not None
        }

#------------------------------------------------------------------

    def topologyUp(self):

        self.CLEANUP_ERRORS = []
        self.CLEANUP_REQUIRED = True
        self._CLEANUP_COMPLETED = set()
        self._PERSISTENT_STATE_COMPLETED = set()
        self.DETAIL = ""
        self.INFRASTRUCTURE.prepare_topology_infrastructure()

        if self.CONFIGURATION.VMS:
            for VMINSTANCE in self.CONFIGURATION.VMS:
                self.VMS[VMINSTANCE.ID] = VMINSTANCE
                createStatus = VMINSTANCE.createVM()
                if createStatus == -1:
                    applyStatus = VMINSTANCE.applyVM()
                    if applyStatus not in (0, None):
                        self.STATUS = applyStatus
                        return applyStatus
                upStatus = VMINSTANCE.upVM()
                if upStatus is None:
                    upStatus = VMINSTANCE.VM_STATUS
                if upStatus != 0:
                    self.STATUS = upStatus
                    return upStatus

        if self.CONFIGURATION.VNFS:
            for VNFINSTANCE in self.CONFIGURATION.VNFS:
                self.VNFS[VNFINSTANCE.ID] = VNFINSTANCE
                createStatus = VNFINSTANCE.createVNF()
                if createStatus == -1:
                    applyStatus = VNFINSTANCE.applyVNF()
                    if applyStatus not in (0, None):
                        self.STATUS = applyStatus
                        return applyStatus
                upStatus = VNFINSTANCE.upVNF()
                if upStatus is None:
                    upStatus = VNFINSTANCE.VNF_STATUS
                if upStatus != 0:
                    self.STATUS = upStatus
                    return upStatus

        if self.CONFIGURATION.CONTAINERS:
            for CONTAINERINSTANCE in self.CONFIGURATION.CONTAINERS:
                self.CONTAINERS[CONTAINERINSTANCE.ID] = CONTAINERINSTANCE
                upStatus = CONTAINERINSTANCE.upContainer()
                if upStatus is None:
                    upStatus = CONTAINERINSTANCE.CONTAINER_STATUS
                if upStatus != 0:
                    self.DETAIL = (
                        "Container "
                        + str(CONTAINERINSTANCE.ID)
                        + " failed to start: "
                        + str(getattr(CONTAINERINSTANCE, "DETAIL", "unknown container error"))
                    )
                    self.STATUS = upStatus
                    return upStatus

        if self.CONFIGURATION.SFCS:
            for SFCINSTANCE in self.CONFIGURATION.SFCS:
                # SFCs are materialized and prepared by RuntimeFactory. Keep
                # them down until the explicit SFC service command starts
                # their concrete VNF instances; merely setting SFC_UP here
                # made an empty SFC appear active and caused upSFC() == -2.
                if getattr(SFCINSTANCE, "SFC_VNFS_CONF", None):
                    continue
                prepare = getattr(SFCINSTANCE, "prepareSFC", None)
                if not callable(prepare):
                    continue
                prepare_status = prepare()
                if prepare_status not in (None, 0):
                    self.STATUS = prepare_status
                    return prepare_status

        if self.mininetPrepare() != 0:
            return

        for CONTROLLER in self.CONTROLLERS:
            self.CONTROLLERS[CONTROLLER].ELEM.start()

        for OVS in self.OVSSWITCHES:
            self.OVSSWITCHES[OVS].ELEM.start([self.CONTROLLERS[self.OVSSWITCHES[OVS].CONTROLLER].ELEM])

        if self.SWITCHES and self.SWITCH_CONTROLLER_ID not in self.CONTROLLERS:
            self.STATUS = -4
            return -4

        for SWITCH in self.SWITCHES:
            self.SWITCHES[SWITCH].ELEM.start([self.CONTROLLERS[self.SWITCH_CONTROLLER_ID].ELEM])

        self.STATUS = 0
        return 0

#------------------------------------------------------------------

    def topologyDown(self):
        cleanupErrors = self._cleanupResources()

        if cleanupErrors:
            self.STATUS = -10
            self.DETAIL = self._cleanupDetail(cleanupErrors)
            return -10

        self.STATUS = None
        self.DETAIL = ""
        return 0

#------------------------------------------------------------------

    def rollbackFailedStart(self):
        startupDetail = self.DETAIL
        cleanupErrors = self._cleanupResources()

        if cleanupErrors:
            self.STATUS = -10
            suffix = "Rollback warnings: " + self._cleanupDetail(cleanupErrors)
            self.DETAIL = (self.DETAIL + " | " if self.DETAIL else "") + suffix
        else:
            self.DETAIL = startupDetail
        return cleanupErrors

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
