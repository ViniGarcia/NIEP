from Parser import *
from Spec import MininetControllerSpec
from InfrastructureRuntime import DEFAULT_INFRASTRUCTURE_RUNTIME
from os import getenv
from mininet.net import Mininet
from mininet.node import Host
from mininet.node import Switch
from mininet.node import OVSSwitch
from mininet.node import Controller, RemoteController
from mininet.link import Link, Intf
from mininet.clean import Cleanup


class Executer:
    def __init__(self, CONFIGURATION):
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
        self.SWITCH_CONTROLLER_ID = None
        self.LOCAL_POX_ENABLED = True
        self.INFRASTRUCTURE = DEFAULT_INFRASTRUCTURE_RUNTIME

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

        self.NET = Mininet(topo=None, build=False)
        Cleanup().cleanup()

        for HOST in self.CONFIGURATION.MNHOSTS:
            HOST.ELEM = self.NET.addHost(HOST.ID)
            self.HOSTS[HOST.ID] = HOST

        for SWITCH in self.CONFIGURATION.MNSWITCHES:
            SWITCH.ELEM = self.NET.addSwitch(SWITCH.ID)
            self.SWITCHES[SWITCH.ID] = SWITCH

        if self.SWITCHES:
            if self.LOCAL_POX_ENABLED:
                self.POX = self.INFRASTRUCTURE.start_local_pox()
                UNICTRL = MininetControllerSpec('UNICTRL', '127.0.0.1', 6633)
                UNICTRL.ELEM = self.NET.addController('UNICTRL', controller=RemoteController, ip='127.0.0.1', port=6633)
                self.CONTROLLERS['UNICTRL'] = UNICTRL
                self.SWITCH_CONTROLLER_ID = 'UNICTRL'
            elif self.CONFIGURATION.MNCONTROLLER:
                self.SWITCH_CONTROLLER_ID = self.CONFIGURATION.MNCONTROLLER[0].ID
            else:
                self.STATUS = -4
                return -4

        for CONTROLLER in self.CONFIGURATION.MNCONTROLLER:
            CONTROLLER.ELEM = self.NET.addController(CONTROLLER.ID, controller=RemoteController, ip=CONTROLLER.IP, port=CONTROLLER.PORT)
            self.CONTROLLERS[CONTROLLER.ID] = CONTROLLER

        for OVS in self.CONFIGURATION.MNOVSES:
            OVS.ELEM = self.NET.addSwitch(OVS.ID)
            self.OVSSWITCHES[OVS.ID] = OVS

        ifacesData = self.interfacesMaping()
        externalEndpoints = self.externalEndpoints()
        for LINK in self.CONFIGURATION.CONNECTIONS:

            if not "IN/OUTIFACE" in LINK and not "OUT/INIFACE" in LINK:

                if LINK["IN/OUT"] in self.SWITCHES:
                    Element01 = self.SWITCHES[LINK["IN/OUT"]]
                else:
                    Element01 = self.OVSSWITCHES[LINK["IN/OUT"]]

                if LINK["OUT/IN"] in self.SWITCHES:
                    Element02 = self.SWITCHES[LINK["OUT/IN"]]
                else:
                    Element02 = self.OVSSWITCHES[LINK["OUT/IN"]]

                self.NET.addLink(Element01.ELEM, Element02.ELEM)
                continue

            if "IN/OUTIFACE" in LINK and not "OUT/INIFACE" in LINK:
                if LINK["IN/OUT"] in externalEndpoints:
                    EXTERNALLINKS = externalEndpoints[LINK["IN/OUT"]]
                    for iface in EXTERNALLINKS.INTERFACES:
                        if iface["MAC"] == LINK["IN/OUTIFACE"]:
                            if iface["ID"] in ifacesData:
                                brName = iface["ID"]
                                virtualIface = ifacesData[iface["ID"]]
                                break
                            else:
                                self.STATUS = -1
                                return -1
                    if LINK["OUT/IN"] in self.SWITCHES:
                        Intf(brName, node = self.SWITCHES[LINK["OUT/IN"]].ELEM)
                    elif LINK["OUT/IN"] in self.OVSSWITCHES:
                        Intf(brName, node = self.OVSSWITCHES[LINK["OUT/IN"]].ELEM)
                    else:
                        self.STATUS = -2
                        return -2
                    continue
                else:
                    Element01 = self.HOSTS[LINK["IN/OUT"]]

                    if LINK["OUT/IN"] in self.SWITCHES:
                        Element02 = self.SWITCHES[LINK["OUT/IN"]]
                    else:
                        Element02 = self.OVSSWITCHES[LINK["OUT/IN"]]

                    NodesLink = self.NET.addLink(Element01.ELEM, Element02.ELEM)
                    HostIface = Element01.ELEM.intf(NodesLink.intf1)
                    HostIface.setMAC(LINK["IN/OUTIFACE"])
                    for iface in Element01.INTERFACES:
                        if iface["MAC"] == LINK["IN/OUTIFACE"]:
                            iface["ELEM"] = HostIface
                            break
                    continue

            if "OUT/INIFACE" in LINK and not "IN/OUTIFACE" in LINK:
                if LINK["OUT/IN"] in externalEndpoints:
                    EXTERNALLINKS = externalEndpoints[LINK["OUT/IN"]]
                    for iface in EXTERNALLINKS.INTERFACES:
                        if iface["MAC"] == LINK["OUT/INIFACE"]:
                            if iface["ID"] in ifacesData:
                                brName = iface["ID"]
                                virtualIface = ifacesData[iface["ID"]]
                                break
                            else:
                                self.STATUS = -1
                                return -1
                    if LINK["IN/OUT"] in self.SWITCHES:
                        Intf(brName, node = self.SWITCHES[LINK["IN/OUT"]].ELEM)
                    elif LINK["IN/OUT"] in self.OVSSWITCHES:
                        Intf(brName, node = self.OVSSWITCHES[LINK["IN/OUT"]].ELEM)
                    else:
                        self.STATUS = -2
                        return -2
                    continue
                else:
                    if LINK["IN/OUT"] in self.SWITCHES:
                        Element01 = self.SWITCHES[LINK["IN/OUT"]]
                    else:
                        Element01 = self.OVSSWITCHES[LINK["IN/OUT"]]

                    Element02 = self.HOSTS[LINK["OUT/IN"]]

                    NodesLink = self.NET.addLink(Element01.ELEM, Element02.ELEM)
                    HostIface = Element01.ELEM.intf(NodesLink.intf2)
                    HostIface.setMAC(LINK["OUT/INIFACE"])
                    for iface in Element02.INTERFACES:
                        if iface["MAC"] == LINK["OUT/INIFACE"]:
                            iface["ELEM"] = HostIface
                            break
                    continue

            else:
                if LINK["IN/OUT"] in self.HOSTS and LINK["OUT/IN"] in self.HOSTS:
                    Element01 = self.HOSTS[LINK["IN/OUT"]]
                    Element02 = self.HOSTS[LINK["OUT/IN"]]

                    NodesLink = self.NET.addLink(Element01.ELEM, Element02.ELEM)
                    HostIface01 = Element01.ELEM.intf(NodesLink.intf1)
                    HostIface02 = Element01.ELEM.intf(NodesLink.intf2)

                    HostIface01.setMAC(LINK["IN/OUTIFACE"])
                    HostIface02.setMAC(LINK["OUT/INIFACE"])

                    for iface in Element01.INTERFACES:
                        if iface["MAC"] == LINK["IN/OUTIFACE"]:
                            iface["ELEM"] = HostIface01
                            break
                    for iface in Element02.INTERFACES:
                        if iface["MAC"] == LINK["OUT/INIFACE"]:
                            iface["ELEM"] = HostIface02
                            break
                    continue

                if LINK["IN/OUT"] in self.HOSTS:
                    Element01 = self.HOSTS[LINK["IN/OUT"]]
                    EXTERNALLINKS = externalEndpoints[LINK["OUT/IN"]]
                    for iface in EXTERNALLINKS.INTERFACES:
                        if iface["MAC"] == LINK["OUT/INIFACE"]:
                            if iface["ID"] in ifacesData:
                                virtualIface = ifacesData[iface["ID"]]
                                break
                            else:
                                self.STATUS = -1
                                return -1

                    HostIface = Intf(virtualIface, node = Element01.ELEM, mac = LINK["IN/OUTIFACE"])
                    for iface in Element01.INTERFACES:
                        if iface["MAC"] == LINK["IN/OUTIFACE"]:
                            iface["ELEM"] = HostIface
                            break
                    continue

                if LINK["OUT/IN"] in self.HOSTS:

                    EXTERNALLINKS = externalEndpoints[LINK["IN/OUT"]]
                    for iface in EXTERNALLINKS.INTERFACES:
                        if iface["MAC"] == LINK["IN/OUTIFACE"]:
                            if iface["ID"] in ifacesData:
                                virtualIface = ifacesData[iface["ID"]]
                                break
                            else:
                                self.STATUS = -1
                                return -1

                    Element02 = self.HOSTS[LINK["OUT/IN"]]
                    HostIface = Intf(virtualIface, node = Element02.ELEM, mac = LINK["OUT/INIFACE"])
                    for iface in Element02.INTERFACES:
                        if iface["MAC"] == LINK["OUT/INIFACE"]:
                            iface["ELEM"] = HostIface
                            break
                    continue

                else:
                    self.STATUS = -3
                    return -3

        self.NET.build()
        for HOST in self.HOSTS:
            DummyIfaces = 0
            for IFACE in self.HOSTS[HOST].INTERFACES:
                if "ELEM" in IFACE: 
                    if IFACE["IP"] != None:
                        IFACE["ELEM"].setIP(IFACE["IP"])
                    else:
                        if IFACE["ELEM"].IP() != None:
                            self.HOSTS[HOST].ELEM.cmd("sudo ip addr flush " + str(IFACE["ELEM"].name))
                else:
                    self.HOSTS[HOST].ELEM.cmd("sudo ip link add mn-eth" + str(DummyIfaces) + " address " + IFACE["MAC"] + " type dummy")
                    if IFACE["IP"] != None:
                        self.HOSTS[HOST].ELEM.cmd("sudo ip addr add " + IFACE["IP"] + " dev " + "mn-eth" + str(DummyIfaces))
                    self.HOSTS[HOST].ELEM.cmd("sudo ifconfig mn-eth" + str(DummyIfaces) + " up") 
                    DummyIfaces += 1
                    
        return 0

#------------------------------------------------------------------

    def topologyUp(self):

        self.CLEANUP_ERRORS = []
        self.CLEANUP_REQUIRED = True
        self._CLEANUP_COMPLETED = set()
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
                SFCINSTANCE.SFC_UP = True

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

        for sfc in list(getattr(self.CONFIGURATION, "SFCS", [])):
            sfcID = getattr(sfc, "ID", "unknown")
            self._attemptCleanup(
                cleanupErrors,
                ("sfc", sfcID, "mark_down"),
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
            cleanupErrors.append(
                self._cleanupError(resourceType, resourceID, operation, str(exc))
            )
            return

        if status not in (0, None):
            nestedErrors = getattr(resource, "CLEANUP_ERRORS", None)
            if nestedErrors:
                cleanupErrors.extend(nestedErrors)
            else:
                message = getattr(resource, "DETAIL", "") or str(status)
                cleanupErrors.append(
                    self._cleanupError(resourceType, resourceID, operation, message)
                )
            return

        self._CLEANUP_COMPLETED.add(cleanupKey)

    def _cleanupError(self, resourceType, resourceID, operation, message):
        return {
            "resource_type": str(resourceType),
            "resource_id": str(resourceID),
            "operation": str(operation),
            "message": str(message),
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
