import json
import random
from VNF import VNF
from os import path

class SFC:
    ID = ''
    VNFS = []
    IP = {}
    OPS = []
    CONNECTIONS = []

    SFC_VNFS_CONF = []
    SFC_VNF_INSTANCES = []
    SFC_LAST_INSTANCES = []

    SFC_UP = False
    SFC_PARCIAL_UP = False
    SFC_STATUS = 0
    SFC_JSON = ''

#__init__: charges the SFC data if JSON exists and call for validation
#          -12 = JSON file not found
    def __init__(self, configurationPath):

        if path.isfile(configurationPath):
            self.SFC_JSON = configurationPath
            with open(self.SFC_JSON) as dataSFC:
                parsedSFC = json.load(dataSFC)
        else:
            self.SFC_STATUS = -12
            return

        if 'ID' in parsedSFC:
            self.ID = parsedSFC['ID']
        if 'VNFS' in parsedSFC:
            self.VNFS = parsedSFC['VNFS']
        if 'IP' in parsedSFC:
            self.IP = parsedSFC['IP']
        if 'OPS' in parsedSFC:
            self.OPS = parsedSFC['OPS']
        if 'CONNECTIONS' in parsedSFC:
            self.CONNECTIONS = parsedSFC['CONNECTIONS']

        if self.structureValidation() == 0:
            self.graphValidation()

#__del__: restores the class to the fundamental state, avoiding same memory
#         allocations problems.
    def __del__(self):

        self.ID = ''
        del self.VNFS[:]
        self.IP.clear()
        del self.OPS[:]
        del self.CONNECTIONS[:]

        del self.SFC_VNFS_CONF[:]
        del self.SFC_VNF_INSTANCES[:]
        del self.SFC_LAST_INSTANCES[:]

        self.SFC_UP = False
        self.SFC_PARCIAL_UP = False
        self.SFC_STATUS = 0
        self.SFC_JSON = ''

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

#structureValidation = verifies all data and check it coherence.
#                       0 = valid structure
#                      -1 = some data is missing
#                      -2 = no use or more than one use for ID in VNFs
#                      -3 = no ID or no LINK in IP
#                      -4 = no ID, ID reuse or no LINK in OPs
#                      -5 = no presence or wrong presence in CONNECTIONS ILL or OLL, duplicated connection
#                      -6 = repeated MAC
    def structureValidation(self):

        if self.ID == '' or self.VNFS == [] or self.IP == {} or self.OPS == [] or self.CONNECTIONS == []:
            self.SFC_STATUS = -1
            return -1

        VNFID = [VNF['ID'] for VNF in self.VNFS]
        OPSID = [OP['ID'] for OP in self.OPS]
        ILLMACS = [MAC['ILL_MAC'] for MAC in self.CONNECTIONS if 'ILL_MAC' in MAC]
        OLLMACS = [MAC['OLL_MAC'] for MAC in self.CONNECTIONS if 'OLL_MAC' in MAC]

        for VNF in self.VNFS:
            if not 'ID' in VNF:
                self.SFC_STATUS = -2
                return -2
            if VNFID.count(VNF['ID']) != 1:
                self.SFC_STATUS = -2
                return -2

        if not 'ID' in self.IP or not 'LINK' in self.IP:
            self.SFC_STATUS = -3
            return -3

        for OP in self.OPS:
            if not 'ID' in OP or not 'LINK' in OP:
                self.SFC_STATUS = -4
                return -4
            if OPSID.count(OP['ID']) != 1:
                self.SFC_STATUS = -4
                return -4

        for CONNECTION in self.CONNECTIONS:
            if not 'ILL' in CONNECTION or not 'OLL' in CONNECTION:
                self.SFC_STATUS = -5
                return -5

            if not 'LINK' in CONNECTION:
                if CONNECTION['OLL'] != self.IP['ID']:
                    if not CONNECTION['ILL'] in OPSID:
                        self.SFC_STATUS = -5
                        return -5
                    else:
                        if not CONNECTION['OLL'] in VNFID or not 'OLL_MAC' in CONNECTION:
                            self.SFC_STATUS = -5
                            return -5
                else:
                    if not CONNECTION['ILL'] in VNFID or not 'ILL_MAC' in CONNECTION:
                        self.SFC_STATUS = -5
                        return -5
            else:
                if not CONNECTION['ILL'] in VNFID or not CONNECTION['OLL'] in VNFID:
                    self.SFC_STATUS = -5
                    return -5
                if not 'ILL_MAC' in CONNECTION or not 'OLL_MAC' in CONNECTION:
                    self.SFC_STATUS = -5
                    return -5
                if 'LINK_MAC' in CONNECTION:
                    if self.__checkMAC(CONNECTION['LINK_MAC']):
                        self.SFC_STATUS = -5
                        return -5
                else:
                    CONNECTION['LINK_MAC'] = self.__randomizeMAC()

            if self.CONNECTIONS.count(CONNECTION) != 1:
                self.SFC_STATUS = -5
                return -5

        for MAC in ILLMACS:
            if ILLMACS.count(MAC) != 1 or MAC in OLLMACS:
                self.SFC_STATUS = -6
                return -6
        for MAC in OLLMACS:
            if OLLMACS.count(MAC) != 1:
                self.SFC_STATUS = -6
                return -6

        self.SFC_STATUS = 0
        return 0

#graphValidation: graph validation for SFC instantiation.
#                  0 =  valid graph
#                 -7 =  problems in Incoming Point (IP)
#                       More than one occurrence
#                       Not present a OLL
#                       Present a ILL
#                       More than one connection in link
#                 -8 =  problems with Outcoming Points (OPs)
#                       Not present a ILL
#                       Present a OLL
#                       Connection with output link in SFC
#                 -9 =  problems with VNFs
#                       Not present a OLL
#                       Not present a ILL
#                 -10 = problems with connections
#                       Loop detected (ILL = OLL)
#                 -11 = problems with links
#                       More than one use (not support shared links yet)
    def graphValidation(self):

        OPSID = [OP['ID'] for OP in self.OPS]
        CONNECTIONSILL = [ILL['ILL'] for ILL in self.CONNECTIONS]
        CONNECTIONSOLL = [OLL['OLL'] for OLL in self.CONNECTIONS]
        CONNECTIONLINK = [LINK['LINK'] for LINK in self.CONNECTIONS if 'LINK' in LINK]

        if CONNECTIONSOLL.count(self.IP['ID']) != 1 or CONNECTIONSILL[CONNECTIONSOLL.index(self.IP['ID'])] in OPSID:
            self.SFC_STATUS = -7
            return -7
        else:
            if self.IP['ID'] in CONNECTIONSILL:
                self.SFC_STATUS = -7
                return -7
            if self.IP['LINK'] in CONNECTIONLINK:
                self.SFC_STATUS = -7
                return -7
            if 'LINK_MAC' in self.IP:
                if self.__checkMAC(self.IP['LINK_MAC']):
                    self.SFC_STATUS = -7
                    return -7
            else:
                self.IP['LINK_MAC'] = self.__randomizeMAC()

        for OP in self.OPS:
            if not OP['ID'] in CONNECTIONSILL:
                self.SFC_STATUS = -8
                return -8
            else:
                if OP['ID'] in CONNECTIONSOLL:
                    self.SFC_STATUS = -8
                    return -8
                if OP['LINK'] in CONNECTIONLINK:
                    self.SFC_STATUS = -8
                    return -8
                if 'LINK_MAC' in OP:
                    if self.__checkMAC(OP['LINK_MAC']):
                        self.SFC_STATUS = -8
                        return -8
                else:
                    OP['LINK_MAC'] = self.__randomizeMAC()

        for VNF in self.VNFS:
            if not VNF['ID'] in CONNECTIONSILL:
                self.SFC_STATUS = -9
                return -9
            if not VNF['ID'] in CONNECTIONSOLL:
                self.SFC_STATUS = -9
                return -9

        for CONNECTION in self.CONNECTIONS:
            if CONNECTION['ILL'] == CONNECTION['OLL']:
                self.SFC_STATUS = -10
                return -10

        for LINK in CONNECTIONLINK:
            if CONNECTIONLINK.count(LINK) != 1:
                self.SFC_STATUS = -11
                return -11

        self.SFC_STATUS = 0
        return 0

#prepareSFC: get the SFC information and organizes all data to up the VNFs.
#            -1 = SFC is up, down it to modify
#             0 = SFC successfully prepared
    def prepareSFC(self):

        if self.SFC_STATUS < 0:
            return

        if self.SFC_UP:
            return -1

        for VNF in self.VNFS:
            CONF = [(VNF['ID'], VNF['PATH'])]
            for CONNECTION in self.CONNECTIONS:
                if 'LINK' in CONNECTION:
                    if CONNECTION['ILL'] == VNF['ID']:
                        CONF.append({'ID':CONNECTION['LINK'], 'MAC':CONNECTION['ILL_MAC'], 'LINK_MAC':CONNECTION['LINK_MAC']})
                        continue
                    if CONNECTION['OLL'] == VNF['ID']:
                        CONF.append({'ID':CONNECTION['LINK'], 'MAC':CONNECTION['OLL_MAC'], 'LINK_MAC':CONNECTION['LINK_MAC']})
                        continue
                else:
                    if CONNECTION['OLL'] == self.IP['ID']:
                        if CONNECTION['ILL'] == VNF['ID']:
                            CONF.append({'ID':self.IP['LINK'], 'MAC':CONNECTION['ILL_MAC'], 'LINK_MAC':self.IP['LINK_MAC']})
                    else:
                        if CONNECTION['OLL'] == VNF['ID']:
                            OP = filter(lambda OP : OP['ID'] == CONNECTION['ILL'], self.OPS)
                            CONF.append({'ID':OP[0]['LINK'], 'MAC':CONNECTION['OLL_MAC'], 'LINK_MAC':OP[0]['LINK_MAC']})
            self.SFC_VNFS_CONF.append(CONF)

        return 0

# modifySFC: reads the SFC JSON to replace the actual configuration.
#            -2 to -12 = (error code + 1) and check it in graph and struct validation
#            -1 = SFC is up, down it to modify
#             0 = SFC successfully modified
    def modifySFC(self):

        if self.SFC_STATUS < 0:
            return

        if self.SFC_UP:
            return -1

        with open(self.SFC_JSON) as dataSFC:
            parsedSFC = json.load(dataSFC)

        if 'VNFS' in parsedSFC:
            self.VNFS = parsedSFC['VNFS']
        if 'IP' in parsedSFC:
            self.IP = parsedSFC['IP']
        if 'OPS' in parsedSFC:
            self.OPS = parsedSFC['OPS']
        if 'CONNECTIONS' in parsedSFC:
            self.CONNECTIONS = parsedSFC['CONNECTIONS']

        self.SFC_VNFS_CONF = []

        check = self.structureValidation()
        if check == 0:
            check = self.graphValidation()
            if check == 0:
                return 0
            else:
                return check - 1
        else:
            return check - 1

#destroyVNF: remove all SFC's VNFs from database deleting all files.
#           -2 = no SFC to destroy
#           -1 = SFC is up, down it to destroy
#            0 = VNF successfully removed
    def destroySFC(self):

        if self.SFC_STATUS < 0:
            return

        if self.SFC_UP:
            return -1

        if self.SFC_LAST_INSTANCES == []:
            return -2

        for INSTANCE in self.SFC_LAST_INSTANCES:
            INSTANCE.destroyVNF()
        self.SFC_LAST_INSTANCES = []

        return 0

#upSFC: up the SFC starting all VNF VMs in KVM hypervisor, when the SFC is killed, the VM will
#       disappear from hypervisor list.
#       [VNF, ERROR] = ERROR occurred on VNF up
#       -2 = SFC does not prepared, prepare it to up
#       -1 = SFC already up
#        0 = SFC upped successfully
    def upSFC(self):

        if self.SFC_STATUS < 0:
            return

        if self.SFC_UP:
            return -1

        if self.SFC_VNFS_CONF == []:
            return -2

        for CONF in self.SFC_VNFS_CONF:
            instace = VNF(CONF[0][1], CONF[1:])
            if instace.VNF_STATUS < 0:
                return [CONF[0][0], instace.VNF_STATUS]
            if instace.VNF_STATUS == 0:
                instace.createVNF()
            self.SFC_VNF_INSTANCES.append(instace)

        for INSTANCE in self.SFC_VNF_INSTANCES:
            check = INSTANCE.upVNF()
            if check != 0:
                for DOWN in self.SFC_VNF_INSTANCES:
                    if DOWN.VNF_UP == True:
                        DOWN.downVNF()
                    else:
                        return [INSTANCE.ID, check]

        self.SFC_UP = True
        return 0

#downSFC: down a started SFC and removes all VNFs from hypervisor list.
#         -1 = SFC already down
#          0 = SFC downed successfully
    def downSFC(self):

        if self.SFC_STATUS < 0:
            return

        if not self.SFC_UP:
            return -1

        for INSTANCE in self.SFC_VNF_INSTANCES:
            INSTANCE.downVNF()

        self.SFC_LAST_INSTANCES = self.SFC_VNF_INSTANCES
        self.SFC_VNF_INSTANCES = []
        self.SFC_UP = False
        return 0

#checkStatusSFC: check if all SFC' VMs are up, if they are it is up,
#                else it is down.
#                True = Up SFC
#                False = Down SFC
    def checkStatusSFC(self):

        downCounter = 0
        for INSTANCE in self.SFC_VNF_INSTANCES:
            if not INSTANCE.VNF_UP: 
                downCounter += 1

        if downCounter > 0:
            self.SFC_UP = False
            if len(self.SFC_VNF_INSTANCES) == downCounter:
                self.SFC_PARCIAL_UP = False
            else:
                self.SFC_PARCIAL_UP = True
            return False

        self.SFC_UP = True
        self.SFC_PARCIAL_UP = True
        return True

#sleepSFC: down the SFC VNFS but does not remove the VMs from the hypervisor, 
#          neither remove the VNFs instances from the VNF instaces list.
#         -1 = SFC already down
#          0 = SFC sleeped successfully
    def sleepSFC(self):

        if self.SFC_STATUS < 0:
            return

        if not self.SFC_UP and not self.SFC_PARCIAL_UP:
            return -1

        for INSTANCE in self.SFC_VNF_INSTANCES:
            INSTANCE.sleepVNF()

        self.SFC_UP = False
        return 0

#wakeSFC: restore sleeped VMs waking the VM.
#         -1 = SFC already up
#          0 = SFC sleeped successfully
    def wakeSFC(self):

        if self.SFC_STATUS < 0:
            return

        if self.SFC_UP:
            return -1

        for INSTANCE in self.SFC_VNF_INSTANCES:
            INSTANCE.upVNF()

        self.SFC_UP = True
        return 0

#managementSFC: get all management interfaces form SFC's VNFs and show to user.
#               -2 = some instance is not accessible
#               -1 = SFC is not up, up it to access VNFs
#               [] = management interfaces returned successfully
    def managementSFC(self):

        if self.SFC_STATUS < 0:
            return

        if not self.SFC_UP:
            return -1

        addressVNF = []
        for INSTANCE in self.SFC_VNF_INSTANCES:
            resultCheck = INSTANCE.managementVNF()
            if isinstance(resultCheck, basestring):
                addressVNF.append(INSTANCE.ID + ' -> ' + resultCheck)
            else:
                return -2

        return addressVNF