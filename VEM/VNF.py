import json

from ClickOnOSv import ClickOnOSv
from os import path

from VM import *

#VNFServer: class for VNFs management.
#Assumptions:
#   - Debian Like Environment
#   - KVM Hypervisor
#   - Virt Manager
#Assumptions Install Settings:
#   - sudo apt-get install qemu-kvm qemu-system
#   - sudo apt-get install virt-manager
#NOTE: EXECUTE THIS SCRIPT IN SUPER USER MODE!!

class VNF:
    ID = ''
    VM = None

    VNF_OPERATOR = None
    
    VNF_UP = False
    VNF_STATUS = 0

# __init__: redirects to the correct function to initialize the class, for file interfaces use set 'interface'
#          as None.
    def __init__(self, configurationPath, interfaces):

        if path.isfile(configurationPath):
            self.VNF_JSON = configurationPath
            with open(self.VNF_JSON) as dataVNF:
                parsedVNF = json.load(dataVNF)
        else:
            self.VNF_STATUS = -1
            return

        if 'ID' in parsedVNF:
            self.ID = parsedVNF['ID']
        if "VM" in parsedVNF:
            if interfaces != None:
                self.VM = VM(parsedVNF["VM"], self.ID, interfaces)
            else:
                self.VM = VM(parsedVNF["VM"], self.ID, None)

        if self.VM.__class__.__name__ != VM.__name__:
            self.VNF_STATUS = -2
            return

#__del__: restores the class to the fundamental state, avoiding same memory
#         allocations problems.
    def __del__(self):
        self.ID = ''
        self.VM = None

        self.VNF_OPERATOR = None

        self.VNF_UP = False
        self.VNF_STATUS = 0

#scriptExecution: execute defined tasks in a json script file.
#                 -1 = Script file does not exist
#                 -2 = Invalid action requested in the script
#                 -3 = Wrong number of arguments for the requested action
    def __scriptExecution(self, scriptPath):

        if not path.isfile(scriptPath):
            return(False, -1)
        
        scriptTasks = []
        scriptFile = [[command.replace('\n', '') for command in line.split(' ')] for line in open(scriptPath).readlines()]
        for line in scriptFile:
            if not line[0] in self.VNF_OPERATOR.VNF_CATALOG:
                return (False, -2)
            if len(line) - 1 != self.VNF_OPERATOR.VNF_CATALOG[line[0]][1]:
                return (False, -3) 

        scriptResults = []
        for line in scriptFile:
            actionResult = self.VNF_OPERATOR.VNF_CATALOG[line[0]][0](*line[1:])
            scriptResults.append(actionResult)
            if not actionResult[0]:
                return (False, scriptResults)

        return (True, scriptResults)

#createVNF: copy data file in VNF does not exist in the database and modify the XML configuration
#           according to received JSON.
#           -1 = VNF already exists
#            0 = VNF successfully created
    def createVNF(self):

        if self.VNF_STATUS < 0:
            return

        return self.VM.createVM()
        
# modifyVNF: reads the VNF JSON to replace the actual configuration.
#            -5 = VNF does not exist, you need create it before apply configurations
#            -4 = problems in INTERFACES data
#            -3 = problems in GENERAL data
#            -2 = the VNF disk can not be changed
#            -1 = VNF is up, down it to modify
#             0 = VNF successfully modified
    def modifyVNF(self):

        if self.VNF_STATUS < 0:
            return

        if self.VNF_UP:
            return -1

        return self.VM.modifyVM()

# destroyVNF: remove the VNF from database deleting all files.
#           -2 = VNF does not exists, so it can't be removed
#           -1 = VNF is up, down it to destroy
#            0 = VNF successfully removed
    def destroyVNF(self):

        if self.VNF_STATUS < 0:
            return

        if self.VNF_UP:
            return -1

        resultVm = self.VM.destroyVM()
        if resultVm == 0:
            self.VNF_STATUS = 0

        return resultVm

#upVNF: starts the VNF VM in KVM hypervisor, it is a temporary VM, so when the VM downs it will
#       disappear from hypervisor list.
#       -2 = VNF does not exist, create it to up
#       -1 = VNF already up
#        0 = VNF upped successfully
    def upVNF(self):

        if self.VNF_STATUS < 0:
            return

        if self.VNF_UP:
            return -1

        resultVm = self.VM.upVM()

        if resultVm == 0:
            self.VNF_UP = True

        return resultVm

#downVNF: down a started VNF and removes from hypervisor list.
#         -2 = VNF does not exist
#         -1 = VNF already down
#          0 = VNF downed successfully
    def downVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        resultVm = self.VM.downVM()

        if resultVm == 0:
            self.VNF_UP = False
            self.VNF_OPERATOR = None

        return resultVm

#sleepVNF: down a started VNF but do not remove from hypervisor neither interfaces.
#         -2 = VNF does not exist
#         -1 = VNF already down
#          0 = VNF downed successfully
    def sleepVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        resultVm = self.VM.sleepVM()

        if resultVm == 0:
            self.VNF_UP = False
            self.VNF_OPERATOR = None

        return resultVm


#managementVNF: get the management interface address by a arp request.
#               -2 = arp did not respond
#               -1 = VNF is not up
#               IP:Port = management address
    def managementVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        return self.VM.managementVM()

#controlVNF: control functions life cycle and get VNFs informations, the action is
#            the expected call and arguments is a list of this call needs.
#            -1    = VNF is no up, up to control it
#            -2    = management not acessible by ARP
#            -3    = action is not available
#            -4    = wrong number of arguments provided
    def controlVNF(self, action, arguments):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        if self.VNF_OPERATOR == None:
            management = self.managementVNF()
            if isinstance(management, basestring):
                self.VNF_OPERATOR = ClickOnOSv(management)
            else:
                return -2

        if action == "list":
            return {key:self.VNF_OPERATOR.VNF_CATALOG[key][2] for key in self.VNF_OPERATOR.VNF_CATALOG}

        if not action in self.VNF_OPERATOR.VNF_CATALOG:
            return -3

        if len(arguments) != self.VNF_OPERATOR.VNF_CATALOG[action][1]:
            return -4
        
        return self.VNF_OPERATOR.VNF_CATALOG[action][0](*arguments)



#scriptVNF: execute a script serialized in a dictionary in scriptNormal, scriptError is
#           another serial tasks set operating as an error handle (it can be None).
#           -1      = VNF is no up, up to control it
#           -2      = management not acessible by ARP
    def scriptVNF(self, scriptNormal, scriptError):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        if self.VNF_OPERATOR == None:
            management = self.managementVNF()
            if isinstance(management, basestring):
                self.VNF_OPERATOR = ClickOnOSv(management)
            else:
                return -2

        normalResult = self.__scriptExecution(scriptNormal)
        if normalResult[0]:
            return (True, [normalResult])

        if scriptError != None:
            errorResult = self.__scriptExecution(scriptError)
            if errorResult[0]:
                return (True, [normalResult, errorResult])
            else:
                return (False, [normalResult, errorResult])

        return (False, [normalResult])