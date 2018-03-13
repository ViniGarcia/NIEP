import json
import libvirt 
from REST import REST
from time import sleep
from glob import glob
from uuid import uuid4
from os import path
from os import devnull
from copy import copy
from subprocess import call
from subprocess import check_output
from xml.etree import ElementTree

#FNULL: redirects the system call normal output
FNULL = open(devnull, 'w')
#STDPATH: standard path - added to be used in NIEP
STDPATH = '../VEM/'
#VIRT_CONNECTION: used to manage the virtual machines creation and exclusion
VIRT_CONNECTION = libvirt.open("qemu:///system")

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
    MEMORY = 0
    VCPU = 0
    MANAGEMENT_MAC = ''
    INTERFACES = []

    VNF_EXIST = False
    VNF_UP = False
    VNF_STATUS = 0

    VNF_JSON = ''
    VNF_REST = None

    VIRT_VM = None

# __init__: redirects to the correct function to initialize the class, for file interfaces use set 'interface'
#          as none.
    def __init__(self, configurationPath, interfaces):

        if interfaces != None:
            self.outInterfaces(configurationPath, interfaces)
        else:
            self.inInterfaces(configurationPath)

#inInterfaces: receives the JSON VNF configuration, parses it, apply data in destiny attributes and
#              validates the read data and check for VNF existence.
#              -5 = file does not exist
    def inInterfaces(self, configurationPath):

        if path.isfile(configurationPath):
            self.VNF_JSON = configurationPath
            with open(self.VNF_JSON) as dataVNF:
                parsedVNF = json.load(dataVNF)
        else:
            self.VNF_STATUS = -5
            return -5

        if 'ID' in parsedVNF:
            self.ID = parsedVNF['ID']
        if 'MEMORY' in parsedVNF:
            self.MEMORY = parsedVNF['MEMORY']
        if 'VCPU' in parsedVNF:
            self.VCPU = parsedVNF['VCPU']
        if 'MANAGEMENT_MAC' in parsedVNF:
            self.MANAGEMENT_MAC = parsedVNF['MANAGEMENT_MAC']
        if 'INTERFACES' in parsedVNF:
            self.INTERFACES = parsedVNF['INTERFACES']

        self.fullValidation()

# outInterfaces : receives the JSON VNF configuration and ignores the interface data, in this case
#                 it receives as argument too, parses it, apply data in destiny attributes and validates
#                 the read data and check for VNF existence.
#                 -5 = file does not exist
    def outInterfaces(self, configurationPath, interfaces):

        if path.isfile(configurationPath):
            self.VNF_JSON = configurationPath
            with open(self.VNF_JSON) as dataVNF:
                parsedVNF = json.load(dataVNF)
        else:
            self.VNF_STATUS = -5
            return -5

        if 'ID' in parsedVNF:
            self.ID = parsedVNF['ID']
        if 'MEMORY' in parsedVNF:
            self.MEMORY = parsedVNF['MEMORY']
        if 'VCPU' in parsedVNF:
            self.VCPU = parsedVNF['VCPU']
        if 'MANAGEMENT_MAC' in parsedVNF:
            self.MANAGEMENT_MAC = parsedVNF['MANAGEMENT_MAC']
        self.INTERFACES = interfaces

        self.fullValidation()

#fullValidation: verify all attributes checking if it contains possible values, check the VNF existence
#          in database.
#          -4 = VNF already exists created by an external agent
#          -3 = VNF already in use by an external agent or other VNFServer instance
#          -2 = problems in INTERFACES data
#          -1 = problems in GENERAL data
#           0 = valid configuration, VNF is not in the database and is free for creation
#           1 = valid configuration, VNF already in the database
    def fullValidation(self):

        if self.ID == '' or self.MEMORY <= 0 or self.VCPU <= 0 or self.MANAGEMENT_MAC == '':
            self.VNF_STATUS = -1
            return -1
        for iface in self.INTERFACES:
            if 'ID' not in iface or 'MAC' not in iface:
                self.VNF_STATUS = -2
                return -2

        existingImages = glob(STDPATH + 'IMAGES/*')
        for images in existingImages:
            if images[14:] == self.ID:
                self.VNF_EXIST = True
                break

        upVMs = check_output(['virsh', 'list']).split('\n')
        for index in range(2, len(upVMs)-2):
            if [VM for VM in upVMs[index].replace(' ', ',').split(',') if VM != ''][1] == self.ID:
                self.VNF_UP = True
                break

        identicalVM = False
        allVMs = check_output(['virsh', 'list', '--all']).split('\n')
        for index in range(2, len(allVMs)-2):
            if [VM for VM in allVMs[index].replace(' ', ',').split(',') if VM != ''][1] == self.ID:
                identicalVM = True
                break

        if self.VNF_EXIST:
            if self.VNF_UP:
                self.VNF_STATUS = -3
                return -3
            else:
                if identicalVM:
                    self.VNF_STATUS = -4
                    return -4
                else:
                    self.VNF_STATUS = 1
                    return 1
        else:
            if identicalVM:
                self.VNF_STATUS = -4
                return -4

        self.VNF_STATUS = 0
        return 0

#modifyValidation: verify only attributes checking if it contains possible values
#                  -2 = problems in INTERFACES data
#                  -1 = problems in GENERAL data
#                   1 = valid configuration, VNF ready for modification
    def modifyValidation(self):

        if self.ID == '' or self.MEMORY <= 0 or self.VCPU <= 0 or self.MANAGEMENT_MAC == '':
            self.VNF_STATUS = -1
            return -1
        for iface in self.INTERFACES:
            if 'ID' not in iface or 'MAC' not in iface:
                self.VNF_STATUS = -2
                return -2

        self.VNF_STATUS = 1
        return 1

#createVNF: copy data file in VNF does not exist in the database and modify the XML configuration
#           according to received JSON.
#           -1 = VNF already exists
#            0 = VNF successfully created
    def createVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_EXIST:
            call(['mkdir', STDPATH + 'IMAGES/' + self.ID])
            call(['cp', STDPATH + 'IMAGES/click-on-osv.qcow2', STDPATH + 'IMAGES/' + self.ID + '/click-on-osv.qcow2'])
            self.VNF_EXIST = True
            self.applyVNF()
            return 0
        else:
            return -1

# modifyVNF: reads the VNF JSON to replace the actual configuration.
#            -4 = VNF does not exist, you need create it before apply configurations
#            -3 = problems in INTERFACES data
#            -2 = problems in GENERAL data
#            -1 = VNF is up, down it to modify
#             0 = VNF successfully modified
    def modifyVNF(self):

        if self.VNF_STATUS < 0:
            return

        if self.VNF_UP:
            return -1

        with open(self.VNF_JSON) as dataVNF:
            parsedVNF = json.load(dataVNF)

        if 'MEMORY' in parsedVNF:
            self.MEMORY = parsedVNF['MEMORY']
        if 'VCPU' in parsedVNF:
            self.VCPU = parsedVNF['VCPU']
        if 'MANAGEMENT_MAC' in parsedVNF:
            self.MANAGEMENT_MAC = parsedVNF['MANAGEMENT_MAC']
        if 'INTERFACES' in parsedVNF:
            self.INTERFACES = parsedVNF['INTERFACES']

        check = self.modifyValidation()
        if check == -1:
            return -2
        if check == -2:
            return -3
        check = self.applyVNF()
        if check == -2:
            return -4
        return 0

# destroyVNF: remove the VNF from database deleting all files.
#           -2 = VNF is up, down it to destroy
#           -1 = VNF does not exists, so it can't be removed
#            0 = VNF successfully removed
    def destroyVNF(self):

        if self.VNF_STATUS < 0:
            return

        if self.VNF_UP:
            return -2

        if self.VNF_EXIST:
            call(['rm', '-r', './IMAGES/' + self.ID])
            self.VNF_EXIST = False
            self.VNF_STATUS = 0
            return 0
        else:
            return -1

#applyVNF: modify the standart XML configuration according to received JSON for VNF deploy.
#           -2 = VNF does not exist, you need create it before apply configurations
#           -1 = VNF is up, down it to modify the configuration
#            0 = configuration successfully set
    def applyVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_EXIST:
            return -2

        if not self.VNF_UP:
            call(['cp', STDPATH + 'IMAGES/click-on-osv.xml', STDPATH + 'IMAGES/' + self.ID + '/click-on-osv.xml'])

            configurationXML = ElementTree.parse(STDPATH + 'IMAGES/' + self.ID + '/click-on-osv.xml')
            configurationXML.find('name').text = self.ID
            configurationXML.find('uuid').text = str(uuid4())
            configurationXML.find('memory').text = str(self.MEMORY * 1024)
            configurationXML.find('currentMemory').text = str(self.MEMORY * 1024)
            configurationXML.find('vcpu').text = str(self.VCPU)
            configurationXML.find('devices/interface/mac').attrib['address'] = self.MANAGEMENT_MAC
            configurationXML.find('devices/disk/source').attrib['file'] = path.abspath(STDPATH + 'IMAGES/' + self.ID + '/click-on-osv.qcow2')

            slotID = bytearray('a')
            for iface in self.INTERFACES:
                interfaceTag = ElementTree.SubElement(configurationXML.find('devices'), 'interface')
                interfaceTag.attrib['type'] = 'bridge'
                interfaceConfig = ElementTree.SubElement(interfaceTag, 'mac')
                interfaceConfig.attrib['address'] = iface['MAC']
                interfaceConfig = ElementTree.SubElement(interfaceTag, 'source')
                interfaceConfig.attrib['bridge'] = iface['ID']
                interfaceConfig = ElementTree.SubElement(interfaceTag, 'model')
                interfaceConfig.attrib['type'] = 'virtio'
                interfaceConfig = ElementTree.SubElement(interfaceTag, 'address')
                interfaceConfig.attrib['type'] = 'pci'
                interfaceConfig.attrib['domain'] = '0x0000'
                interfaceConfig.attrib['bus'] = '0x00'
                interfaceConfig.attrib['slot'] = '0x0' + str(slotID)
                interfaceConfig.attrib['function'] = '0x0'
                slotID[0] += 1

            configurationXML.write(STDPATH + 'IMAGES/' + self.ID + '/click-on-osv.xml')
            return 0
        else:
            return -1

#upVNF: starts the VNF VM in KVM hypervisor, it is a temporary VM, so when the VM downs it will
#       disappear from hypervisor list.
#       -2 = VNF does not exist, create it to up
#       -1 = VNF already up
#        0 = VNF upped successfully
    def upVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_EXIST:
            return -2

        if not self.VNF_UP:
            ifacesData = check_output(['brctl', 'show']).split('\n')
            ifacesCreate = copy(self.INTERFACES)
            for iface in self.INTERFACES:
                for iface2 in ifacesData:
                    if iface2.startswith(iface['ID']):    
                        ifacesCreate.remove(iface)

            for iface in ifacesCreate:
                call(['brctl', 'addbr', iface['ID']])
            for iface in self.INTERFACES:
                call(['ifconfig', iface['ID'], 'up'])

            with open(STDPATH + 'IMAGES/' + self.ID + '/click-on-osv.xml', 'r') as domainFile:
                domainXML = domainFile.read()
            VIRT_CONNECTION.defineXML(domainXML)
            self.VIRT_VM = VIRT_CONNECTION.lookupByName(self.ID)
            self.VIRT_VM.create()
            self.VNF_UP = True
            return 0
        else:
            return -1

#downVNF: down a started VNF and removes from hypervisor list.
#         -2 = VNF does not exist
#         -1 = VNF already down
#          0 = VNF downed successfully
    def downVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_EXIST:
            return -2

        if self.VNF_UP:
            self.VIRT_VM.destroy()
            self.VIRT_VM.undefine()
            self.VIRT_VM = None
            self.VNF_UP = False
            self.VNF_REST = None
            for iface in self.INTERFACES:
                call(['ifconfig', iface['ID'], 'down'])
                call(['brctl', 'delbr', iface['ID']])
            return 0
        else:
            return -1

#sleepVNF: down a started VNF but do not remove from hypervisor neither interfaces.
#         -2 = VNF does not exist
#         -1 = VNF already down
#          0 = VNF downed successfully
    def sleepVNF(self):

        if self.VNF_STATUS < 0:
            return

        if not self.VNF_EXIST:
            return -2

        if self.VNF_UP:
            self.VIRT_VM.destroy()
            self.VIRT_VM = None
            self.VNF_UP = False
            self.VNF_REST = None
            return 0
        else:
            return -1


#managementVNF: get the management interface address by a arp request.
#               -2 = arp did not respond
#               -1 = VNF is not up
#               IP:Port = management address
    def managementVNF(self):

        if self.VNF_STATUS < 0:
            return

        if self.VNF_UP:
            for attempt in range(0,3):
                arpData = check_output(['arp', '-n']).split('\n')
                for index in range(1,len(arpData)-1):
                    iface = [data for data in arpData[index].replace(' ', ',').split(',') if data != '']
                    if iface[2] == self.MANAGEMENT_MAC:
                        return iface[0] + ':8000'
                sleep(2)
        else:
            return -1

        return -2

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