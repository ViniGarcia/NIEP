from Parser import *
from mininet.node import Host
from mininet.node import Switch
from mininet.node import OVSSwitch
from mininet.node import Controller
from mininet.link import Link

class Executer:
    CONFIGURATION = None
    HOSTS = {}
    SWITCHES = {}
    OVSSWITCHES = {}
    CONTROLLERS = {}

    def __init__(self, CONFIGURATION):

        self.CONFIGURATION = CONFIGURATION

#------------------------------------------------------------------

    def mininetPrepare(self):

        #if self.CONFIGURATION.VNFS:
        #    VMCTRL = MNController('VMCTRL')
        #    VMCTRL.ELEM = Controller('VMCTRL', inNamespace=False)
        #    self.CONTROLLERS['VMCTRL'] = VMCTRL

        #    VMACC = MNOVSES('VMACC', 'VMCTRL')
        #    VMACC.ELEM = OVSSwitch(VMACC.ID, inNamespace=False)
        #    self.OVSSWITCHES['VMACC'] = VMACC

        #    for VNFINSTANCE in self.CONFIGURATION.VNFS:
        #        VNFINSTANCE.createVNF()

        for HOST in self.CONFIGURATION.MNHOSTS:
            HOST.ELEM = Host(HOST.ID)
            self.HOSTS[HOST.ID] = HOST

        for SWITCH in self.CONFIGURATION.MNSWITCHES:
            SWITCH.ELEM = OVSSwitch(SWITCH.ID, inNamespace=False)
            self.SWITCHES[SWITCH.ID] = SWITCH

        if self.SWITCHES:
            UNICTRL = MNController('UNICTRL')
            UNICTRL.ELEM = Controller('UNICTRL', inNamespace=False)
            self.CONTROLLERS['UNICTRL'] = UNICTRL

        for CONTROLLER in self.CONFIGURATION.MNCONTROLLER:
            CONTROLLER.ELEM = Controller(CONTROLLER.ID, inNamespace=False)
            self.CONTROLLERS[CONTROLLERS.ID] = CONTROLLER

        for OVS in self.CONFIGURATION.MNOVSES:
            OVS.ELEM = OVSSwitch(OVS.ID, inNamespace=False)
            self.OVSSWITCHES[OVS.ID] = OVS

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

                Link(Element01.ELEM, Element02.ELEM)

                if LINK["IN/OUT"] in self.HOSTS:
                    self.HOSTS[LINK["IN/OUT"]].ELEM.setIP(self.HOSTS[LINK["IN/OUT"]].IP)
                if LINK["OUT/IN"] in self.HOSTS:
                    self.HOSTS[LINK["OUT/IN"]].ELEM.setIP(self.HOSTS[LINK["OUT/IN"]].IP)
            else:
                print 'TO DO'


#------------------------------------------------------------------

    def topologyUp(self):

        #for VNFINSTANCE in self.CONFIGURATION.VNFS:
        #    VNFINSTANCE.upVNF()

        for CONTROLLER in self.CONTROLLERS:
            self.CONTROLLERS[CONTROLLER].ELEM.start()

        for OVS in self.OVSSWITCHES:
            self.OVSSWITCHES[OVS].ELEM.start([self.CONTROLLERS[self.OVSSWITCHES[OVS].CONTROLLER].ELEM])

        for SWITCH in self.SWITCHES:
            self.SWITCHES[SWITCH].ELEM.start([self.CONTROLLERS['UNICTRL'].ELEM])

#------------------------------------------------------------------

    def topologyDown(self):

        #for VNFINSTANCE in self.CONFIGURATION.VNFS:
        #    VNFINSTANCE.downVNF()

        for OVS in self.OVSSWITCHES:
            self.OVSSWITCHES[OVS].ELEM.stop()

        for CONTROLLER in self.CONTROLLERS:
            self.CONTROLLERS[CONTROLLER].ELEM.stop()

        for SWITCH in self.SWITCHES:
            self.SWITCHES[SWITCH].ELEM.stop()
#------------------------------------------------------------------

PSR = PlatformParser("/home/gt-fende/Documentos/NIEP/EXAMPLES/DEFINITIONS/Functional.json")
EXE = Executer(PSR)
EXE.mininetPrepare()
EXE.topologyUp()
raw_input('Enter your input:')
print EXE.HOSTS["HOST01"].ELEM.IP()
print EXE.HOSTS["HOST01"].ELEM.cmd('ping -c1', "192.168.122.02")
EXE.topologyDown()