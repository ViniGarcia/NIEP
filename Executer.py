from Parser import PlatformParser
from mininet.net import Mininet
from mininet.cli import CLI

class Executer:
    CONFIGURATION = None
    NET = None

    def __init__(self, CONFIGURATION):

        self.CONFIGURATION = CONFIGURATION

#------------------------------------------------------------------

    def VNFSPrepare(self):

        for VNFINSTANCE in self.CONFIGURATION.VNFS:
            VNFINSTANCE.createVNF()

#------------------------------------------------------------------

    def mininetPrepare(self):

        self.NET = Mininet()

        for HOST in self.CONFIGURATION.MNHOSTS:
            HOST.ELEM = self.NET.addHost(HOST.ID)
            HOST.ELEM.setIP(HOST.IP)

        for SWITCH in self.CONFIGURATION.MNSWITCHES:
            SWITCH.ELEM = self.NET.addSwitch(SWITCH.ID)

        for CONTROLLER in self.CONFIGURATION.MNCONTROLLERS:
            CONTROLLER.ELEM = self.NET.addController(CONTROLLER.ID)

        for OVS in self.MNOVSES:
            OVS.ELEM = self.NET.addSwitch(OVS.ID)

#------------------------------------------------------------------

    def connectionsPrepare(self):
        print ("NOT IMPLEMENTED YET")

#------------------------------------------------------------------

    def topologyStart(self):

        for VNFINSTANCE in self.CONFIGURATION.VNFS:
            VNFINSTANCE.upVNF()
        self.NET.start()

#------------------------------------------------------------------

PSR = PlatformParser("Teste01.json")
EXE = Executer(PSR)
EXE.VNFSStart()