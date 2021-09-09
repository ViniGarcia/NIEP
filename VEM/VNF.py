import json

from REST import REST
from os import path

from VM import *

#VNFServer: class for Click-On-OSv VNFs management.
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

    VNF_REST = None
    
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

        self.VNF_REST = None

        self.VNF_UP = False
        self.VNF_STATUS = 0

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
            self.VNF_REST = None

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
            self.VNF_REST = None

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
#            the expected RESTfull call and arguments is a list of this call needs,
#            actually, only 'function_replace' uses to pass the function file.
#            -1    = VNF is no up, up to control it
#            -2    = management not acessible by ARP
#            other = check REST.py file
    def controlVNF(self, action, arguments):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        if self.VNF_REST == None:
            management = self.managementVNF()
            if isinstance(management, basestring):
                self.VNF_REST = REST(management)
            else:
                return -2

        if action == 'function_start':
            return self.VNF_REST.postStart()
        if action == 'function_stop':
            return self.VNF_REST.postStop()
        if action == 'function_replace':
            return self.VNF_REST.postFunction(arguments[0])
        if action == 'function_run':
            return self.VNF_REST.getRunning()
        if action == 'function_data':
            return self.VNF_REST.getFunction()
        if action == 'function_id':
            return self.VNF_REST.getIdentification()
        if action == 'function_metrics':
            return self.VNF_REST.getMetrics()
        if action == 'function_log':
            return self.VNF_REST.getLog()

#scriptVNF: execute a script serialized in a dictionary in scriptTasks, scriptError is
#           another serial tasks set as a error handle (can be None), finally, functionPath is for
#           replace actions, it can be None.
#            []     = seccessfull execution, REST results is presented
#           -1      = VNF is no up, up to control it
#           -2      = management not acessible by ARP
#           -3 ~ -8 = analog to REST.scriptExecution + 2 result
    def scriptVNF(self, scriptTasks, scriptError, functionPath):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_UP:
            return -1

        if self.VNF_REST == None:
            management = self.managementVNF()
            if isinstance(management, basestring):
                self.VNF_REST = REST(management)
            else:
                return -2

        resultCheck = self.VNF_REST.scriptExecution(scriptTasks, scriptError, functionPath)
        if isinstance(resultCheck, list):
            return resultCheck
        else:
            if resultCheck < 0:
                return resultCheck - 2
            else:
                return resultCheck

"""
#Simple CLI interface to test the library, if not necessay comment it.
def help():
    print('\n================== CLI INTERFACE ==================')
    print('up -> UP VNF SERVER')
    print('down -> DOWN VNF SERVER')
    print('modify -> APLLY NEW CONFIGURATIONS SET IN VNF JSON')
    print('destroy -> DESTROY VNF SERVER FILES')
    print('management -> GET THE MANAGEMENT ADDRESS')
    print('help -> SHOW THIS INFORMATION')
    print('quit -> END PROGRAM AND DOWN VNF (IF IT\'S NOT)')
    print('===================================================')

VNFPath = raw_input('VNF JSON PATH: ')

VNF = VNF(VNFPath, None)
if (VNF.VNF_STATUS < 0):
    print 'ERROR ' + VNF.VNF_STATUS + ' OCCURED IN VALIDATION!!'
else:
    if (VNF.VNF_STATUS == 0):
        VNF.createVNF()
    running = True
    help()
    while running:
        option = raw_input('OPERATION: ')
        if option == 'up':
            resultCheck = VNF.upVNF()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN upVNF')
            continue
        if option == 'down':
            resultCheck = VNF.downVNF()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN downVNF')
            continue
        if option == 'modify':
            resultCheck = VNF.modifyVNF()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN modifyVNF')
            continue
        if option == 'destroy':
            resultCheck = VNF.destroyVNF()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN destroyVNF')
            continue
        if option == 'management':
            resultCheck = VNF.managementVNF()
            if isinstance(resultCheck, basestring):
                print resultCheck
            else:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN managementVNF')
            continue
        if option == 'help':
            help()
            continue
        if option == 'quit':
            if VNF.VNF_UP:
                VNF.downVNF()
            running = False
            continue
"""