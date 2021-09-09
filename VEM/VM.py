import json
import random
import libvirt 
from time import sleep
from glob import glob
from uuid import uuid4
from os import path
from os import devnull
from copy import copy
from subprocess import call
from subprocess import check_output
from subprocess import STDOUT
from xml.etree import ElementTree

#FNULL: redirects the system call normal output
FNULL = open(devnull, 'w')
#STDPATH: standard path - added to be used in NIEP
STDPATH = '/'.join(path.abspath(__file__).split('/')[:-1]) + '/'
#VIRT_CONNECTION: used to manage the virtual machines creation and exclusion
VIRT_CONNECTION = libvirt.open("qemu:///system")

#VM: class for generic VMs management.
#Assumptions:
#   - Linux-like Environment
#   - KVM Hypervisor
#   - Virt Manager
#Assumptions Install Settings:
#   - sudo apt-get install qemu-kvm qemu-system
#   - sudo apt-get install virt-manager
#NOTE: EXECUTE THIS SCRIPT IN SUPER USER MODE!!

class VM:
    ID = ''
    MEMORY = 0
    VCPU = 0
    DISK = ''
    MANAGEMENT_MAC = ''
    INTERFACES = []

    VM_EXIST = False
    VM_UP = False
    VM_STATUS = 0

    VM_JSON = ''

    VIRT_VM = None

# __init__: redirects to the correct function to initialize the class, for file interfaces use set 'interface'
#          as none.
    def __init__(self, configurationPath, alias, interfaces):

        if interfaces != None:
            self.outInterfaces(configurationPath, alias, interfaces)
        else:
            self.inInterfaces(configurationPath, alias)

#__del__: restores the class to the fundamental state, avoiding same memory
#         allocations problems.
    def __del__(self):
        self.ID = ''
        self.MEMORY = 0
        self.VCPU = 0
        self.DISK = ''
        self.MANAGEMENT_MAC = ''
        del self.INTERFACES[:]

        self.VM_EXIST = False
        self.VM_UP = False
        self.VM_STATUS = 0

        self.VM_JSON = ''

        self.VIRT_VM = None

#__checkMAC = verifies a given MAC address and return if it is valid or not.
#              0 = valid MAC
#             -1 = invalid MAC
    def __checkMAC(self, MAC):

        if isinstance(MAC, basestring) and len(MAC) == 17:
            for i in range(2, 16, 3):
                if MAC[i] != ':':
                    return -1
            for i in range(0, 16, 2):
                if (ord(MAC[i]) < 48 and ord(MAC[i]) > 57) and (ord(MAC[i]) < 65 and ord(MAC[i]) > 70) and (ord(MAC[i]) < 97 and ord(MAC[i]) > 66):
                    return -1
            for i in range(1, 16, 2):
                if (ord(MAC[i]) < 48 and ord(MAC[i]) > 57) and (ord(MAC[i]) < 65 and ord(MAC[i]) > 70) and (ord(MAC[i]) < 97 and ord(MAC[i]) > 66):
                    return -1
        else:
            return -1

        return 0

#__randomizeMAC = creates a new random MAC address for internal usage.
#                   str = valid MAC address
    def __randomizeMAC(self):

        MACValues = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f"]
        MACString = "00:"

        while True:
            MACString = MACString + MACValues[random.randint(0, 15)] + MACValues[random.randint(0, 15)]
            if len(MACString) == 17:
                break
            MACString = MACString + ":"

        return MACString

#inInterfaces: receives the JSON VM configuration, parses it, apply data in destiny attributes and
#              validates the read data and check for VM existence.
#              -1 = VM file does not exist
    def inInterfaces(self, configurationPath, alias):

        if path.isfile(configurationPath):
            self.VM_JSON = configurationPath
            with open(self.VM_JSON) as dataVM:
                parsedVM = json.load(dataVM)
        else:
            self.VM_STATUS = -1
            return -1

        if alias != None:
            self.ID = alias
        elif 'ID' in parsedVM:
            self.ID = parsedVM['ID']
        if 'MEMORY' in parsedVM:
            self.MEMORY = parsedVM['MEMORY']
        if 'VCPU' in parsedVM:
            self.VCPU = parsedVM['VCPU']
        if 'DISK' in parsedVM:
            self.DISK = parsedVM['DISK']
        if 'MANAGEMENT_MAC' in parsedVM:
            self.MANAGEMENT_MAC = parsedVM['MANAGEMENT_MAC']
        if 'INTERFACES' in parsedVM:
            self.INTERFACES = parsedVM['INTERFACES']

        self.fullValidation()

# outInterfaces : receives the JSON VM configuration and ignores the interface data, in this case it
#                 receives as argument too, parses it, apply data in destiny attributes and validates
#                 the read data and check for VM existence.
#                 -1 = VM file does not exist
    def outInterfaces(self, configurationPath, alias, interfaces):

        if path.isfile(configurationPath):
            self.VM_JSON = configurationPath
            with open(self.VM_JSON) as dataVM:
                parsedVM = json.load(dataVM)
        else:
            self.VM_STATUS = -1
            return -1

        if alias != None:
            self.ID = alias
        elif 'ID' in parsedVM:
            self.ID = parsedVM['ID']
        if 'MEMORY' in parsedVM:
            self.MEMORY = parsedVM['MEMORY']
        if 'VCPU' in parsedVM:
            self.VCPU = parsedVM['VCPU']
        if 'DISK' in parsedVM:
            self.DISK = parsedVM['DISK']
        if 'MANAGEMENT_MAC' in parsedVM:
            self.MANAGEMENT_MAC = parsedVM['MANAGEMENT_MAC']
        self.INTERFACES = interfaces

        self.fullValidation()

#fullValidation: verify all attributes checking if it contains possible values, check the VM existence
#          in database.
#          -8 = VM already exists created by an external agent
#          -7 = VM already in use by an external agent or other VM Server instance
#          -6 = problems with INTERFACES data
#          -5 = invalid MANAGEMENT_MAC
#          -4 = invalid DISK
#          -3 = invalid VCPU
#          -2 = invalid MEMORY
#          -1 = invalid ID
#           0 = valid configuration, VM is not in the database and is free for creation
#           1 = valid configuration, VM already in the database
    def fullValidation(self):

        if self.ID == '': 
            self.VM_STATUS = -1
            return -1
        if self.MEMORY <= 0:
            self.VM_STATUS = -2
            return -2
        if self.VCPU <= 0:
            self.VM_STATUS = -3
            return -3
        if not self.DISK in ['tinycore12', 'click-on-osv']:
            return -4
        if self.MANAGEMENT_MAC == '':
            return -5

        for iface in self.INTERFACES:
            if 'ID' not in iface or 'MAC' not in iface:
                self.VM_STATUS = -6
                return -6
            if 'LINK_MAC' in iface:
                if self.__checkMAC(iface['LINK_MAC']):
                    self.VM_STATUS = -6
                    return -6
            else:
                iface['LINK_MAC'] = self.__randomizeMAC()

        existingImages = glob(STDPATH + 'IMAGES/*')
        for images in existingImages:
            if images.split("/")[-1] == self.ID:
                self.VM_EXIST = True
                break

        upVMs = check_output(['virsh', 'list']).split('\n')
        for index in range(2, len(upVMs)-2):
            if [VM for VM in upVMs[index].replace(' ', ',').split(',') if VM != ''][1] == self.ID:
                self.VM_UP = True
                break

        identicalVM = False
        allVMs = check_output(['virsh', 'list', '--all']).split('\n')
        for index in range(2, len(allVMs)-2):
            if [VM for VM in allVMs[index].replace(' ', ',').split(',') if VM != ''][1] == self.ID:
                identicalVM = True
                break

        if self.VM_EXIST:
            if self.VM_UP:
                self.VM_STATUS = -7
                return -7
            else:
                if identicalVM:
                    self.VM_STATUS = -8
                    return -8
                else:
                    self.VM_STATUS = 1
                    return 1
        else:
            if identicalVM:
                self.VM_STATUS = -8
                return -8

        self.VM_STATUS = 0
        return 0

#modifyValidation: verify only attributes checking if it contains possible values
#                  -6 = problems with INTERFACES data
#                  -5 = invalid MANAGEMENT_MAC
#                  -4 = invalid DISK
#                  -3 = invalid VCPU
#                  -2 = invalid MEMORY
#                  -1 = invalid ID
#                   1 = valid configuration, VM ready for modification
    def modifyValidation(self):

        if self.ID == '': 
            self.VM_STATUS = -1
            return -1
        if self.MEMORY <= 0:
            self.VM_STATUS = -2
            return -2
        if self.VCPU <= 0:
            self.VM_STATUS = -3
            return -3
        if not self.DISK in ['tinycore12', 'click-on-osv']:
            return -4
        if self.MANAGEMENT_MAC == '':
            return -5

        for iface in self.INTERFACES:
            if 'ID' not in iface or 'MAC' not in iface:
                self.VM_STATUS = -6
                return -6
            if 'LINK_MAC' in iface:
                if self.__checkMAC(iface['LINK_MAC']):
                    self.VM_STATUS = -6
                    return -6

        self.VM_STATUS = 1
        return 1

#createVM: copy data file in VM does not exist in the database and modify the XML configuration
#           according to received JSON.
#           -2 = VM already exists
#           -1 = VM image does not exist
#            0 = VM successfully created
#currently available disks:
#           - tinycore12
#           - click-on-osv
    def createVM(self):

        if self.VM_STATUS < 0:
            return

        if not path.isfile(STDPATH + 'IMAGES/' + self.DISK + '.qcow2'):
            return -1

        if not self.VM_EXIST:
            call(['mkdir', STDPATH + 'IMAGES/' + self.ID], stdout=FNULL, stderr=STDOUT)
            call(['cp', STDPATH + 'IMAGES/' + self.DISK + '.qcow2', STDPATH + 'IMAGES/' + self.ID + '/' + self.DISK + '.qcow2'], stdout=FNULL, stderr=STDOUT)
            self.VM_EXIST = True
            self.applyVM()
            return 0
        else:
            return -2

# modifyVM: reads the VM JSON to replace the actual configuration.
#            -5 = VM does not exist, you need create it before apply configurations
#            -4 = problems in INTERFACES data
#            -3 = problems in GENERAL data
#            -2 = the VM disk can not be changed
#            -1 = VM is up, down it to modify
#             0 = VM successfully modified
    def modifyVM(self):

        if self.VM_STATUS < 0:
            return

        if self.VM_UP:
            return -1

        with open(self.VM_JSON) as dataVM:
            parsedVM = json.load(dataVM)

        if "DISK" in parsedVM:
            if self.DISK != parsedVM["DISK"]:
                return -2

        if 'MEMORY' in parsedVM:
            self.MEMORY = parsedVM['MEMORY']
        if 'VCPU' in parsedVM:
            self.VCPU = parsedVM['VCPU']
        if 'MANAGEMENT_MAC' in parsedVM:
            self.MANAGEMENT_MAC = parsedVM['MANAGEMENT_MAC']
        if 'INTERFACES' in parsedVM:
            self.INTERFACES = parsedVM['INTERFACES']

        check = self.modifyValidation()
        if check == -1:
            return -3
        if check == -2:
            return -4
        check = self.applyVM()
        if check == -2:
            return -5
        return 0

# destroyVM: remove the VM from database deleting all files.
#           -2 = VM does not exists, so it can't be removed
#           -1 = VM is up, down it to destroy
#            0 = VM successfully removed
    def destroyVM(self):

        if self.VM_STATUS < 0:
            return

        if self.VM_UP:
            return -1

        if self.VM_EXIST:
            call(['rm', '-r', './IMAGES/' + self.ID], stdout=FNULL, stderr=STDOUT)
            self.VM_EXIST = False
            self.VM_STATUS = 0
            return 0
        else:
            return -2

#applyVM: modify the standart XML configuration according to received JSON for VM deploying.
#           -2 = VM does not exist, you need create it before apply configurations
#           -1 = VM is up, down it to modify the configuration
#            0 = configuration successfully set
    def applyVM(self):

        if self.VM_STATUS < 0:
            return

        if not self.VM_EXIST:
            return -2

        if not self.VM_UP:
            call(['cp', STDPATH + 'IMAGES/' + self.DISK + '.xml', STDPATH + 'IMAGES/' + self.ID + '/' + self.DISK + '.xml'], stdout=FNULL, stderr=STDOUT)

            configurationXML = ElementTree.parse(STDPATH + 'IMAGES/' + self.ID + '/' + self.DISK + '.xml')
            configurationXML.find('name').text = self.ID
            configurationXML.find('uuid').text = str(uuid4())
            configurationXML.find('memory').text = str(self.MEMORY * 1024)
            configurationXML.find('currentMemory').text = str(self.MEMORY * 1024)
            configurationXML.find('vcpu').text = str(self.VCPU)
            configurationXML.find('devices/interface/mac').attrib['address'] = self.MANAGEMENT_MAC
            configurationXML.find('devices/disk/source').attrib['file'] = path.abspath(STDPATH + 'IMAGES/' + self.ID + '/' + self.DISK + '.qcow2')

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

            configurationXML.write(STDPATH + 'IMAGES/' + self.ID + '/' + self.DISK + '.xml')
            return 0
        else:
            return -1

#upVM: starts the VM in KVM hypervisor, it is a temporary VM, so when the VM downs it will
#       disappear from hypervisor list.
#       -2 = VM does not exist, create it to up
#       -1 = VM already up
#        0 = VM upped successfully
    def upVM(self):

        if self.VM_STATUS < 0:
            return

        if not self.VM_EXIST:
            return -2

        if not self.VM_UP:
            ifacesData = check_output(['brctl', 'show']).split('\n')
            ifacesCreate = copy(self.INTERFACES)
            for iface in self.INTERFACES:
                for iface2 in ifacesData:
                    if iface2.startswith(iface['ID']):    
                        ifacesCreate.remove(iface)

            for iface in ifacesCreate:
                call(['brctl', 'addbr', iface['ID']], stdout=FNULL, stderr=STDOUT)
                call(['ifconfig', iface['ID'], "hw", "ether", iface['LINK_MAC']], stdout=FNULL, stderr=STDOUT)
            for iface in self.INTERFACES:
                call(['ifconfig', iface['ID'], 'up'], stdout=FNULL, stderr=STDOUT)

            with open(STDPATH + 'IMAGES/' + self.ID + '/' + self.DISK + '.xml', 'r') as domainFile:
                domainXML = domainFile.read()
            VIRT_CONNECTION.defineXML(domainXML)
            self.VIRT_VM = VIRT_CONNECTION.lookupByName(self.ID)
            self.VIRT_VM.create()
            self.VM_UP = True
            return 0
        else:
            return -1

#downVM: down a started VM and removes from hypervisor list.
#         -2 = VM does not exist
#         -1 = VM already down
#          0 = VM downed successfully
    def downVM(self):

        if self.VM_STATUS < 0:
            return

        if not self.VM_EXIST:
            return -2

        if self.VM_UP:
            self.VIRT_VM.destroy()
            self.VIRT_VM.undefine()
            self.VIRT_VM = None
            self.VM_UP = False
            for iface in self.INTERFACES:
                call(['ifconfig', iface['ID'], 'down'], stdout=FNULL, stderr=STDOUT)
                call(['brctl', 'delbr', iface['ID']], stdout=FNULL, stderr=STDOUT)
            return 0
        else:
            return -1

#sleepVM: down a started VM but do not remove from hypervisor neither interfaces.
#         -2 = VM does not exist
#         -1 = VM already down
#          0 = VM downed successfully
    def sleepVM(self):

        if self.VM_STATUS < 0:
            return

        if not self.VM_EXIST:
            return -2

        if self.VM_UP:
            self.VIRT_VM.destroy()
            self.VIRT_VM = None
            self.VM_UP = False
            return 0
        else:
            return -1


#managementVM: get the management interface address by a arp request.
#               -2 = arp did not respond
#               -1 = VM is not up
#               IP:Port = management address
    def managementVM(self):

        if self.VM_STATUS < 0:
            return

        if self.VM_UP:
            for attempt in range(0,3):
                arpData = check_output(['arp', '-n']).split('\n')
                for index in range(1,len(arpData)-1):
                    iface = [data for data in arpData[index].replace(' ', ',').split(',') if data != '']
                    if iface[2] == self.MANAGEMENT_MAC:
                        return iface[0]
                sleep(2)
        else:
            return -1

        return -2

"""
#Simple CLI interface to test the library, if not necessay comment it.
def help():
    print('\n================== CLI INTERFACE ==================')
    print('up -> UP VM')
    print('down -> DOWN VM')
    print('modify -> APLLY NEW CONFIGURATIONS SET IN VM JSON')
    print('destroy -> DESTROY VM FILES')
    print('management -> GET VM MANAGEMENT ADDRESS')
    print('help -> SHOW THIS INFORMATION')
    print('quit -> END PROGRAM AND DOWN VM (IF IT\'S NOT)')
    print('===================================================')

VMPath = raw_input('VM JSON PATH: ')

VMI = VM(VMPath, None)
if (VMI.VM_STATUS < 0):
    print 'ERROR ' + str(VMI.VM_STATUS) + ' OCCURED IN VALIDATION!!'
else:
    if (VMI.VM_STATUS == 0):
        VMI.createVM()
    running = True
    help()
    while running:
        option = raw_input('OPERATION: ')
        if option == 'up':
            resultCheck = VMI.upVM()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN upVM')
            continue
        if option == 'down':
            resultCheck = VMI.downVM()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN downVM')
            continue
        if option == 'modify':
            resultCheck = VMI.modifyVM()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN modifyVM')
            continue
        if option == 'destroy':
            resultCheck = VMI.destroyVM()
            if resultCheck < 0:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN destroyVM')
            continue
        if option == 'management':
            resultCheck = VMI.managementVM()
            if isinstance(resultCheck, basestring):
                print resultCheck
            else:
                print ('ERROR ' + str(resultCheck) + ' OCCURED IN managementVM')
            continue
        if option == 'help':
            help()
            continue
        if option == 'quit':
            if VMI.VM_UP:
                VMI.downVM()
            running = False
            continue
"""