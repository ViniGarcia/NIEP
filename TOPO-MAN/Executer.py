from Parser import *
from subprocess import check_output
from subprocess import call, Popen
from subprocess import STDOUT
from os import devnull
from time import sleep
from mininet.net import Mininet
from mininet.node import Host
from mininet.node import Switch
from mininet.node import OVSSwitch
from mininet.node import Controller, RemoteController
from mininet.link import Link, Intf

#FNULL: redirects the system call normal output
FNULL = open(devnull, 'w')

class Executer:
    CONFIGURATION = None
    HOSTS = {}
    SWITCHES = {}
    OVSSWITCHES = {}
    CONTROLLERS = {}
    VNFS = {}
    POX = None 
    NET = None
    STATUS = None

    def __init__(self, CONFIGURATION):

        if CONFIGURATION.STATUS == 0:
            self.CONFIGURATION = CONFIGURATION
        else:
            self.STATUS = -4

    def __del__(self):
        
        self.CONFIGURATION = None
        self.HOSTS.clear()
        self.SWITCHES.clear()
        self.OVSSWITCHES.clear()
        self.CONTROLLERS.clear()
        self.VNFS.clear()
        self.NET = None
        self.STATUS = None

#------------------------------------------------------------------

    def interfacesMaping(self):
        ifacesDictionary = {}

        ifacesData = check_output(['brctl', 'show']).split('\n')
        for iface in ifacesData[1:-1]:
            iface = iface.split('\t')
            ifacesDictionary[iface[0]] = iface[5]

        return ifacesDictionary

#------------------------------------------------------------------

    def mininetPrepare(self):

        self.NET = Mininet(topo=None, build=False)

        for HOST in self.CONFIGURATION.MNHOSTS:
            HOST.ELEM = self.NET.addHost(HOST.ID, mac=HOST.MAC) 
            self.HOSTS[HOST.ID] = HOST

        for SWITCH in self.CONFIGURATION.MNSWITCHES:
            SWITCH.ELEM = self.NET.addSwitch(SWITCH.ID)
            self.SWITCHES[SWITCH.ID] = SWITCH

        if self.SWITCHES:
            self.POX = Popen(['python', '/'.join(abspath(__file__).split('/')[:-2]) + '/OFCONTROLLERS/pox/pox.py', 'forwarding.l2_learning'], stdout=FNULL, stderr=STDOUT)
            sleep(3)
            UNICTRL = MNController('UNICTRL', '127.0.0.1', 6633)
            UNICTRL.ELEM = self.NET.addController('UNICTRL', controller=RemoteController, ip='127.0.0.1', port=6633)
            self.CONTROLLERS['UNICTRL'] = UNICTRL

        for CONTROLLER in self.CONFIGURATION.MNCONTROLLER:
            CONTROLLER.ELEM = self.NET.addController(CONTROLLER.ID, controller=RemoteController, ip=CONTROLLER.IP, port=CONTROLLER.PORT)
            self.CONTROLLERS[CONTROLLER.ID] = CONTROLLER

        for OVS in self.CONFIGURATION.MNOVSES:
            OVS.ELEM = self.NET.addSwitch(OVS.ID)
            self.OVSSWITCHES[OVS.ID] = OVS

        ifacesData = self.interfacesMaping()
        for LINK in self.CONFIGURATION.CONNECTIONS:
            if not "IN/OUTIFACE" in LINK and not "OUT/INIFACE" in LINK:
                if LINK["IN/OUT"] in self.HOSTS:
                    Element01 = self.HOSTS[LINK["IN/OUT"]]
                else:
                    if LINK["IN/OUT"] in self.SWITCHES:
                        Element01 = self.SWITCHES[LINK["IN/OUT"]]
                    else:
                        Element01 = self.OVSSWITCHES[LINK["IN/OUT"]]

                if LINK["OUT/IN"] in self.HOSTS:
                    Element02 = self.HOSTS[LINK["OUT/IN"]]
                else:
                    if LINK["OUT/IN"] in self.SWITCHES:
                        Element02 = self.SWITCHES[LINK["OUT/IN"]]
                    else:
                        Element02 = self.OVSSWITCHES[LINK["OUT/IN"]]

                self.NET.addLink(Element01.ELEM, Element02.ELEM)
            else:
                if "IN/OUTIFACE" in LINK and not "OUT/INIFACE" in LINK:
                    for iface in self.VNFS[LINK["IN/OUT"]].INTERFACES:
                        if iface["MAC"] == LINK["IN/OUTIFACE"]:
                            if iface["ID"] in ifacesData:
                                brName = iface["ID"]
                                virtualIface = ifacesData[iface["ID"]]
                                break
                            else:
                                self.STATUS = -1
                                return -1
                    if LINK["OUT/IN"] in self.HOSTS:
                        Intf(virtualIface, node = self.HOSTS[LINK["OUT/IN"]].ELEM)
                    else:
                        if LINK["OUT/IN"] in self.SWITCHES:
                            Intf(brName, node = self.SWITCHES[LINK["OUT/IN"]].ELEM)
                        else:
                            if LINK["OUT/IN"] in self.OVSSWITCHES:
                                Intf(brName, node = self.OVSSWITCHES[LINK["OUT/IN"]].ELEM)
                            else:
                                self.STATUS = -2
                                return -2
                else:
                    if "OUT/INIFACE" in LINK and not "IN/OUTIFACE" in LINK:
                        for iface in self.VNFS[LINK["OUT/IN"]].INTERFACES:
                            if iface["MAC"] == LINK["OUT/INIFACE"]:
                                if iface["ID"] in ifacesData:
                                    brName = iface["ID"]
                                    virtualIface = ifacesData[iface["ID"]]
                                    break
                                else:
                                    self.STATUS = -1
                                    return -1
                        if LINK["IN/OUT"] in self.HOSTS:
                            Intf(virtualIface, node = self.HOSTS[LINK["IN/OUT"]].ELEM)
                        else:
                            if LINK["IN/OUT"] in self.SWITCHES:
                                Intf(brName, node = self.SWITCHES[LINK["IN/OUT"]].ELEM)
                            else:
                                if LINK["IN/OUT"] in self.OVSSWITCHES:
                                    Intf(brName, node = self.OVSSWITCHES[LINK["IN/OUT"]].ELEM)
                                else:
                                    self.STATUS = -2
                                    return -2
                    else:
                        self.STATUS = -3
                        return -3
        
        self.NET.build()
        for HOST in self.HOSTS:
            if not self.HOSTS[HOST].IP is None:
                self.HOSTS[HOST].ELEM.setIP(self.HOSTS[HOST].IP)
#            if not self.HOSTS[HOST].MAC is None:
#                print("--", self.HOSTS[HOST].MAC)
#                print(self.HOSTS[HOST].ELEM.setMAC(self.HOSTS[HOST].MAC))

        return 0

#------------------------------------------------------------------

    def topologyUp(self):

        checked = False
        ifacesData = check_output(['brctl', 'show']).split('\n')
        for iface in ifacesData:
            if iface.startswith('vbrNIEP'):
                checked = True
                break
        if not checked:
            call(['brctl', 'addbr', 'vbrNIEP'], stdout=FNULL, stderr=STDOUT)
        else:
            checked = False

        netData = check_output(['virsh', 'net-list']).split('\n')
        for net in netData:
            if net.startswith(' vnNIEP'):
                checked = True
                if not net.split('               ')[1].startswith('active'):
                    call(['virsh', 'net-start', 'vnNIEP'], stdout=FNULL, stderr=STDOUT)
                break
        if not checked:
            call(['virsh', 'net-create', '../CONFS/vnNIEP.xml'], stdout=FNULL, stderr=STDOUT)

        if self.CONFIGURATION.VNFS:
            for VNFINSTANCE in self.CONFIGURATION.VNFS:
                if VNFINSTANCE.createVNF() == -1:
                    VNFINSTANCE.applyVNF()
                VNFINSTANCE.upVNF()
                self.VNFS[VNFINSTANCE.ID] = VNFINSTANCE

        if self.CONFIGURATION.SFCS:
            for SFCINSTANCE in self.CONFIGURATION.SFCS:
                SFCINSTANCE.SFC_UP = True

        if self.mininetPrepare() != 0:
            return

        for CONTROLLER in self.CONTROLLERS:
            self.CONTROLLERS[CONTROLLER].ELEM.start()

        for OVS in self.OVSSWITCHES:
            self.OVSSWITCHES[OVS].ELEM.start([self.CONTROLLERS[self.OVSSWITCHES[OVS].CONTROLLER].ELEM])

        for SWITCH in self.SWITCHES:
            self.SWITCHES[SWITCH].ELEM.start([self.CONTROLLERS['UNICTRL'].ELEM])

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

        if type(self.POX) == Popen:
            self.POX.terminate()

        call(['virsh', 'net-destroy', 'vnNIEP'], stdout=FNULL, stderr=STDOUT)
        call(['ifconfig', 'vbrNIEP', 'down'], stdout=FNULL, stderr=STDOUT)
        call(['brctl', 'delbr', 'vbrNIEP'], stdout=FNULL, stderr=STDOUT)

        for VNFINSTANCE in self.CONFIGURATION.VNFS:
            VNFINSTANCE.downVNF()

        for SFCINSTANCE in self.CONFIGURATION.SFCS:
            SFCINSTANCE.SFC_UP = False

        self.STATUS = None

#------------------------------------------------------------------