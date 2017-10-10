from Parser import PlatformParser

class Executer:
    CONFIGURATION = None
    MININETCOMPONENTS = []

    def __init__(self, CONFIGURATION):

        self.CONFIGURATION = CONFIGURATION

#------------------------------------------------------------------

    def VNFSStart(self):

        for VNFINSTANCE in self.CONFIGURATION.VNFS:
            VNFINSTANCE.createVNF()
            VNFINSTANCE.upVNF()

#------------------------------------------------------------------

PSR = PlatformParser("Teste01.json")
EXE = Executer(PSR)
EXE.VNFSStart()