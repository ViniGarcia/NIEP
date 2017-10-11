from Parser import PlatformParser
from mininet.net import Mininet
from mininet.cli import CLI

class Executer:
    CONFIGURATION = None
    NET = None

    def __init__(self, CONFIGURATION):

        self.CONFIGURATION = CONFIGURATION

#------------------------------------------------------------------

    def executerPrepare(self):

	for VNFINSTANCE in self.CONFIGURATION.VNFS:
		VNFINSTANCE.createVNF()

        self.NET = Mininet()

        for HOST in self.CONFIGURATION.MNHOSTS:
            HOST.ELEM = self.NET.addHost(HOST.ID)

        for SWITCH in self.CONFIGURATION.MNSWITCHES:
            SWITCH.ELEM = self.NET.addSwitch(SWITCH.ID)

        for CONTROLLER in self.CONFIGURATION.MNCONTROLLER:
            CONTROLLER.ELEM = self.NET.addController(CONTROLLER.ID)

        for OVS in self.CONFIGURATION.MNOVSES:
            OVS.ELEM = self.NET.addSwitch(OVS.ID)

#------------------------------------------------------------------

    def connectionsPrepare(self):
        
	if self.NET == None:
		return -1

	for LINK in self.CONFIGURATION.CONNECTIONS:
		if not "IN/OUTIFACE" in LINK and not "OUT/INIFACE" in LINK:
			self.NET.addLink(LINK["IN/OUT"], LINK["OUT/IN"])

#------------------------------------------------------------------

    def topologyUp(self):

        for VNFINSTANCE in self.CONFIGURATION.VNFS:
            VNFINSTANCE.upVNF()
        self.NET.start()

#------------------------------------------------------------------

PSR = PlatformParser("Teste01.json")
EXE = Executer(PSR)
EXE.executerPrepare()
EXE.connectionsPrepare()
EXE.topologyUp()
