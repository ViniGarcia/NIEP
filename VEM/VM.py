import json
import random
from uuid import uuid4
from os import path
from xml.etree import ElementTree
from LibvirtRuntime import DEFAULT_LIBVIRT_RUNTIME
from VMImageStore import VMImageStore
from VMNetworkRuntime import DEFAULT_VM_NETWORK_RUNTIME

#STDPATH: standard path - added to be used in NIEP
STDPATH = '/'.join(path.abspath(__file__).split('/')[:-1]) + '/'

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

# __init__: redirects to the correct function to initialize the class, for file interfaces use set 'interface'
#          as none.
    def __init__(self, configurationPath, alias, interfaces):
        self.ID = ''
        self.MEMORY = 0
        self.VCPU = 0
        self.DISK = ''
        self.MANAGEMENT_MAC = ''
        self.INTERFACES = []
        self.VM_EXIST = False
        self.VM_UP = False
        self.VM_STATUS = 0
        self.VM_JSON = ''
        self.VIRT_VM = None
        self.RUNTIME = DEFAULT_LIBVIRT_RUNTIME
        self.IMAGE_STORE = VMImageStore(STDPATH)
        self.NETWORK = DEFAULT_VM_NETWORK_RUNTIME

        if interfaces != None:
            self.outInterfaces(configurationPath, alias, interfaces)
        else:
            self.inInterfaces(configurationPath, alias)

#__checkMAC = verifies a given MAC address and return if it is valid or not.
#              0 = valid MAC
#             -1 = invalid MAC
    def __checkMAC(self, MAC):

        if isinstance(MAC, str) and len(MAC) == 17:
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
            self.VM_STATUS = -4
            return -4
        if self.MANAGEMENT_MAC == '':
            self.VM_STATUS = -5
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

        self.VM_EXIST = self.IMAGE_STORE.instance_exists(self.ID)
        self.VM_UP = self.RUNTIME.is_running(self.ID)
        identicalVM = self.RUNTIME.exists(self.ID)

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
            self.VM_STATUS = -4
            return -4
        if self.MANAGEMENT_MAC == '':
            self.VM_STATUS = -5
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

        if not self.IMAGE_STORE.base_disk_exists(self.DISK):
            return -1

        if not self.VM_EXIST:
            self.IMAGE_STORE.create_instance(self.ID, self.DISK)
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
            self.IMAGE_STORE.remove_instance(self.ID)
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
            self.IMAGE_STORE.copy_template_xml(self.ID, self.DISK)

            configurationXML = ElementTree.parse(self.IMAGE_STORE.instance_xml_path(self.ID, self.DISK))
            configurationXML.find('name').text = self.ID
            configurationXML.find('uuid').text = str(uuid4())
            configurationXML.find('memory').text = str(self.MEMORY * 1024)
            configurationXML.find('currentMemory').text = str(self.MEMORY * 1024)
            configurationXML.find('vcpu').text = str(self.VCPU)
            configurationXML.find('devices/interface/mac').attrib['address'] = self.MANAGEMENT_MAC
            configurationXML.find('devices/disk/source').attrib['file'] = path.abspath(self.IMAGE_STORE.instance_disk_path(self.ID, self.DISK))

            slotID = 0x0a
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
                interfaceConfig.attrib['slot'] = '0x%02x' % slotID
                interfaceConfig.attrib['function'] = '0x0'
                slotID += 1

            configurationXML.write(self.IMAGE_STORE.instance_xml_path(self.ID, self.DISK))
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
            self.NETWORK.prepare_interfaces(self.INTERFACES)
            domainXML = self.IMAGE_STORE.read_domain_xml(self.ID, self.DISK)
            self.VIRT_VM = self.RUNTIME.define_and_create(self.ID, domainXML)
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
            self.RUNTIME.destroy(self.VIRT_VM)
            self.RUNTIME.undefine(self.VIRT_VM)
            self.VIRT_VM = None
            self.VM_UP = False
            self.NETWORK.release_interfaces(self.INTERFACES)
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
            self.RUNTIME.destroy(self.VIRT_VM)
            self.VIRT_VM = None
            self.VM_UP = False
            return 0
        else:
            return -1


#managementVM: get the management interface address by a arp request.
#               -2 = arp did not respond
#               -1 = VM is not up
#               IP = management address
    def managementVM(self):

        if self.VM_STATUS < 0:
            return

        if self.VM_UP:
            managementIp = self.NETWORK.management_ip(self.MANAGEMENT_MAC)
            if managementIp is not None:
                return managementIp
        else:
            return -1

        return -2

#sshVM: try to establish a ssh connection with the VM.
#       -3 = ssh failed
#       -2 = could not retrieve management IP
#       -1 = VM is not up
#        0 = success
    def sshVM(self, user, passwd):
        if self.VM_STATUS < 0:
            return

        if self.VM_UP:
            managementIp = self.managementVM()
            if type(managementIp) != str:
                return -2
            self.NETWORK.ssh(user, passwd, managementIp)
            return 0
        else:
            return -1

        return -3
