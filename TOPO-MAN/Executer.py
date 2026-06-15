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

        self.INFRASTRUCTURE.prepare_topology_infrastructure()

        if self.CONFIGURATION.VMS:
            for VMINSTANCE in self.CONFIGURATION.VMS:
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
                self.VMS[VMINSTANCE.ID] = VMINSTANCE

        if self.CONFIGURATION.VNFS:
            for VNFINSTANCE in self.CONFIGURATION.VNFS:
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
                self.VNFS[VNFINSTANCE.ID] = VNFINSTANCE

        if self.CONFIGURATION.CONTAINERS:
            for CONTAINERINSTANCE in self.CONFIGURATION.CONTAINERS:
                upStatus = CONTAINERINSTANCE.upContainer()
                if upStatus is None:
                    upStatus = CONTAINERINSTANCE.CONTAINER_STATUS
                if upStatus != 0:
                    self.STATUS = upStatus
                    return upStatus
                self.CONTAINERS[CONTAINERINSTANCE.ID] = CONTAINERINSTANCE

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

        if self.STATUS != 0:
            return

        for OVS in self.OVSSWITCHES:
            self.OVSSWITCHES[OVS].ELEM.stop()

        for CONTROLLER in self.CONTROLLERS:
            self.CONTROLLERS[CONTROLLER].ELEM.stop()

        for SWITCH in self.SWITCHES:
            self.SWITCHES[SWITCH].ELEM.stop()

        self.INFRASTRUCTURE.stop_process(self.POX)
        self.INFRASTRUCTURE.cleanup_topology_infrastructure()

        for VMINSTANCE in self.CONFIGURATION.VMS:
            VMINSTANCE.downVM()

        for VNFINSTANCE in self.CONFIGURATION.VNFS:
            VNFINSTANCE.downVNF()

        for CONTAINERINSTANCE in self.CONFIGURATION.CONTAINERS:
            CONTAINERINSTANCE.downContainer()

        for SFCINSTANCE in self.CONFIGURATION.SFCS:
            SFCINSTANCE.SFC_UP = False

        self.STATUS = None

#------------------------------------------------------------------
