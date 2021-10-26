import re
import json
import random
from sys import path
from os.path import isfile, abspath

path.insert(0, '/'.join(abspath(__file__).split('/')[:-2] + ['VEM']))
from VNF import VNF
from SFC import SFC
from VM import VM

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# TO DO LIST

#Detect error when the same interface (MAC) is used to link multiple
#connections in CONNECTIONS of topology definitions.

#Detect the usage of VMs with alias, and block the usage of the VM
#original ID to other elements.

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class MNHost:
    ID = ""
    INTERFACES = None
    ELEM = None

    def __init__(self, ID, INTERFACES):
        self.ID = ID
        self.INTERFACES = INTERFACES

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class MNSwitch:
    ID = ""
    ELEM = None

    def __init__(self, ID):
        self.ID = ID

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class MNController:
    ID = ""
    IP = ""
    PORT = None
    ELEM = None

    def __init__(self, ID, IP, PORT):
        self.ID = ID
        self.IP = IP
        self.PORT = PORT

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class MNOVSSwitch:
    ID = ""
    CONTROLLER = None
    ELEM = None

    def __init__(self, ID, CONTROLLER):
        self.ID = ID
        self.CONTROLLER = CONTROLLER

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class PlatformParser:
    JSON = None
    STATUS = None
    ID = ""
    VMS = []
    VNFS = []
    SFCS = []
    MNHOSTS = []
    MNSWITCHES = []
    MNCONTROLLER = []
    MNOVSES = []
    CONNECTIONS = []

    def __init__(self, jsonFilePath):

        if isfile(jsonFilePath):
            with open(jsonFilePath) as data:
                self.JSON = json.load(data)
        else:
            self.STATUS = -1
            return

        if 'ID' not in self.JSON:
            self.STATUS = -1
            return
        if 'VMS' not in self.JSON:
            self.STATUS = -1
            return   
        if 'VNFS' not in self.JSON:
            self.STATUS = -1
            return
        if 'SFCS' not in self.JSON:
            self.STATUS = -1
            return
        if 'MININET' not in self.JSON:
            self.STATUS = -1
            return

        if isinstance(self.JSON['ID'], basestring):
            self.ID = self.JSON['ID']
        else:
            self.STATUS = -2
            return

        if self.STATUS == None:
            if self.VMSCheck() == 0:
                SFCVNFS = self.SFCCheck()
                if isinstance(SFCVNFS, dict):
                    if self.VNFSCheck(SFCVNFS) == 0:
                        if self.mininetCheck() == 0:
                            if self.connectionsCheck() == 0:
                                self.STATUS = 0

    def __del__(self):

        self.JSON = None
        self.STATUS = None
        self.ID = ""
        del self.VMS[:]
        del self.VNFS[:]
        del self.SFCS[:]
        del self.MNHOSTS[:]
        del self.MNSWITCHES[:]
        del self.MNCONTROLLER[:]
        del self.MNOVSES[:]
        del self.CONNECTIONS[:]

#------------------------------------------------------------------

    def checkIP(self, IP):

        if re.match("^([01]?\\d\\d?|2[0-4]\\d|25[0-5])(?:\\.[01]?\\d\\d?|\\.2[0-4]\\d|\\.25[0-5]){3}(?:/[0-2]\\d|/3[0-2])?$", IP):
            return 0

        return -1

#------------------------------------------------------------------

    def checkMAC(self, MAC):

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

#------------------------------------------------------------------

    def generateMAC(self, lastDigitsTuple):

        MACMask = "ff:ff:ff:ff:ff:"
        if lastDigitsTuple < 10:
            MACMask += "0" + str(lastDigitsTuple)
            return MACMask
        else:
            if lastDigitsTuple < 100:
                MACMask += str(lastDigitsTuple)
                return MACMask
            else:
                self.STATUS = -5
                return -5

#------------------------------------------------------------------

    def randomizeMAC(self):

        MACValues = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f"]
        MACString = "b0:"

        while True:
            MACString = MACString + MACValues[random.randint(0, 15)] + MACValues[random.randint(0, 15)]
            if len(MACString) == 17:
                break
            MACString = MACString + ":"

        return MACString

#------------------------------------------------------------------

    def isint(self, s):
        try:
            int(s)
            return True
        except ValueError:
            return False

#------------------------------------------------------------------
#TODO [VINICIUS - 30/08/21]: Add security tests to duplicate IDs (will raise a KVM error if an ID is duplicated)

    def VMSCheck(self):

        for VMPATH in self.JSON['VMS']:
            if isinstance(VMPATH, basestring) and isfile(VMPATH):
                instance = VM(VMPATH, None, None)
                if instance.VM_STATUS < 0:
                    self.STATUS = -3
                    return -3
                self.VMS.append(instance)
            else:
                self.STATUS = -2
                return -2

        return 0

#------------------------------------------------------------------

    def VNFSCheck(self, SFCVNFS):

        VERIFIEDSFCVNFS = {}
        for SFCID in SFCVNFS:
            for VNFID in SFCVNFS[SFCID]:
                if SFCVNFS[SFCID][VNFID]["PATH"] not in self.JSON['VNFS']:                                        #VNF REDEFINITION, FIRST ASSUMED
                    if SFCVNFS[SFCID][VNFID]["PATH"] not in VERIFIEDSFCVNFS:                                      #VNF REDEFINITION, FIRST ASSUMED
                        VERIFIEDSFCVNFS[SFCVNFS[SFCID][VNFID]["PATH"]] = SFCVNFS[SFCID][VNFID]["CONNECTIONS"]

        PATHINSTANCE = {}
        for VNFPATH in self.JSON['VNFS']:
            if isinstance(VNFPATH, basestring) and isfile(VNFPATH):
                instance = VNF(VNFPATH, None)
                if instance.VNF_STATUS < 0:
                    self.STATUS = -3
                    return -3
                self.VNFS.append(instance)
                PATHINSTANCE[VNFPATH] = instance
            else:
                self.STATUS = -2
                return -2
 
        for VNFPATH in VERIFIEDSFCVNFS:
            if isfile(VNFPATH):
                instance = VNF(VNFPATH, VERIFIEDSFCVNFS[VNFPATH])
                if instance.VNF_STATUS < 0:
                    self.STATUS = -3
                    return -3
                self.VNFS.append(instance)
                PATHINSTANCE[VNFPATH] = instance
            else:
                self.STATUS = -2
                return -2


        for SFCINSTANCE in self.SFCS:
            SFCPATHS = [VNFPATH['PATH'] for VNFPATH in SFCINSTANCE.VNFS]
            for PATH in PATHINSTANCE:
                if PATH in SFCPATHS:
                    SFCINSTANCE.SFC_VNF_INSTANCES.append(PATHINSTANCE[PATH])
                    
        return 0

#------------------------------------------------------------------

    def SFCCheck(self):

        SFCVNFS = {}
        SFCDIC = {}
        for SFCPATH in self.JSON['SFCS']:
            if isinstance(SFCPATH, basestring) and isfile(SFCPATH):
                instance = SFC(SFCPATH)
                if instance.SFC_STATUS < 0:
                    self.STATUS = -5
                    return -5
                if instance.prepareSFC() < 0:
                    self.STATUS = -5
                    return -5
                self.SFCS.append(instance)

                for VNFCONF in instance.SFC_VNFS_CONF:
                    if VNFCONF[0][0] not in SFCVNFS:                                                    #VNF REDEFINITION, FIRST ASSUMED
                        SFCVNFS[VNFCONF[0][0]] = {"PATH":VNFCONF[0][1], "CONNECTIONS":VNFCONF[1:]}
                    else:
                        self.STATUS = -5
                        return -5
                SFCDIC[instance.ID] = SFCVNFS
                SFCVNFS = []
            else:
                self.STATUS = -4
                return -4

        return SFCDIC

#------------------------------------------------------------------

    def mininetCheck(self):

        if isinstance(self.JSON['MININET'], dict):
            MininetList = self.JSON['MININET']
        else:
            self.STATUS = -6
            return -6

        IDLIST = ['UNICTRL']
        CONTROLLERLIST = []
        if "HOSTS" in MininetList:
            if isinstance(MininetList["HOSTS"], list):
                for HOST in MininetList["HOSTS"]:
                    if "ID" in HOST and "INTERFACES" in HOST:

                        if isinstance(HOST["INTERFACES"], list):
                            for IFACE in HOST["INTERFACES"]:
                                if isinstance(IFACE, dict):
                                    if "MAC" in IFACE and "IP" in IFACE:
                                        if IFACE["MAC"] != None:
                                            if self.checkMAC(IFACE["MAC"]):
                                                self.STATUS = -7
                                                return -7
                                        else:
                                            self.STATUS = -7
                                            return -7
                                        if IFACE["IP"] != None:
                                            if self.checkIP(IFACE["IP"]):
                                                self.STATUS = -7
                                                return -7
                                    else:
                                        self.STATUS = -7
                                        return -7
                                else:
                                    self.STATUS = -7
                                    return -7
                        else:
                            self.STATUS = -7
                            return -7
                        
                        
                        if HOST["ID"] in IDLIST:
                            self.STATUS = -7
                            return -7
                        else:
                            IDLIST.append(HOST["ID"])
                    else:
                        self.STATUS = -7
                        return -7

                    self.MNHOSTS.append(MNHost(HOST["ID"], HOST["INTERFACES"]))
            else:
                self.STATUS = -7
                return -7

        if "SWITCHES" in MininetList:
            if isinstance(MininetList["SWITCHES"], list):
                for SWITCH in MininetList["SWITCHES"]:
                    if SWITCH in IDLIST:
                        self.STATUS = -8
                        return -8
                    else:
                        IDLIST.append(SWITCH)

                    self.MNSWITCHES.append(MNSwitch(SWITCH))

        if "CONTROLLERS" in MininetList:
            if isinstance(MininetList["CONTROLLERS"], list):
                for CONTROLLER in MininetList["CONTROLLERS"]:
                    if not "ID" in  CONTROLLER or not "IP" in CONTROLLER or not "PORT" in CONTROLLER or CONTROLLER in IDLIST:
                        self.STATUS = -9
                        return -9
                    else:
                        if not self.isint(CONTROLLER["PORT"]):
                            self.STATUS = -9
                            return -9
                        CONTROLLERLIST.append(CONTROLLER["ID"])

                    self.MNCONTROLLER.append(MNController(CONTROLLER["ID"], CONTROLLER["IP"], int(CONTROLLER["PORT"])))

        if "OVSWITCHES" in MininetList:
            if isinstance(MininetList["OVSWITCHES"], list):
                for OVSSWITCH in MininetList["OVSWITCHES"]:
                    if "ID" in OVSSWITCH and "CONTROLLER" in OVSSWITCH:
                        if OVSSWITCH["ID"] in IDLIST or OVSSWITCH["ID"] in CONTROLLERLIST:
                            self.STATUS = -10
                            return -10
                        else:
                            if OVSSWITCH["CONTROLLER"] in CONTROLLERLIST:
                                IDLIST.append(OVSSWITCH["ID"])
                            else:
                                self.STATUS = -10
                                return -10
                    else:
                        self.STATUS = -10
                        return -10

                    self.MNOVSES.append(MNOVSSwitch(OVSSWITCH["ID"], OVSSWITCH["CONTROLLER"]))

        return 0

# ------------------------------------------------------------------

    def connectionsCheck(self):

        VMSSUMMARY = {VMINSTANCE.ID:VMINSTANCE for VMINSTANCE in self.VMS}
        HOSTSSUMMARY = {HOSTINSTANCE.ID:HOSTINSTANCE for HOSTINSTANCE in self.MNHOSTS}
        for VNFINSTANCE in self.VNFS:
            VMSSUMMARY[VNFINSTANCE.ID] = VNFINSTANCE.VM
        SWITCHESIDS = [SWITCH.ID for SWITCH in self.MNSWITCHES]
        OVSSWITCHESIDS = [OVS.ID for OVS in self.MNOVSES]

        if isinstance(self.JSON['CONNECTIONS'], list):
            ConnectionsList = self.JSON['CONNECTIONS']
        else:
            self.STATUS = -11
            return -11

        for CONNECTION in ConnectionsList:
            if "IN/OUT" in CONNECTION:
                if CONNECTION["IN/OUT"] in VMSSUMMARY:
                    if "IN/OUTIFACE" in CONNECTION:
                        if not any(CONNECTION["IN/OUTIFACE"] == IFACE["MAC"] for IFACE in VMSSUMMARY[CONNECTION["IN/OUT"]].INTERFACES):
                            self.STATUS = -12
                            return -12
                    else:
                        self.STATUS = -12
                        return -12
                elif CONNECTION["IN/OUT"] in HOSTSSUMMARY:
                    if "IN/OUTIFACE" in CONNECTION:
                        if not any(CONNECTION["IN/OUTIFACE"] == IFACE["MAC"] for IFACE in HOSTSSUMMARY[CONNECTION["IN/OUT"]].INTERFACES):
                            self.STATUS = -12
                            return -12
                    else:
                        self.STATUS = -12
                        return -12
                else:
                    if CONNECTION["IN/OUT"] not in SWITCHESIDS and CONNECTION["IN/OUT"] not in OVSSWITCHESIDS:
                        self.STATUS = -12
                        return -12
            else:
                self.STATUS = -12
                return -12

            if "OUT/IN" in CONNECTION:
                if CONNECTION["OUT/IN"] in VMSSUMMARY:
                    if "OUT/INIFACE" in CONNECTION:
                        if not any(CONNECTION["OUT/INIFACE"] == IFACE["MAC"] for IFACE in VMSSUMMARY[CONNECTION["OUT/IN"]].INTERFACES):
                            self.STATUS = -13
                            return -13
                    else:
                        self.STATUS = -13
                        return -13
                elif CONNECTION["OUT/IN"] in HOSTSSUMMARY:
                    if "OUT/INIFACE" in CONNECTION:
                        if not any(CONNECTION["OUT/INIFACE"] == IFACE["MAC"] for IFACE in HOSTSSUMMARY[CONNECTION["OUT/IN"]].INTERFACES):
                            self.STATUS = -13
                            return -13
                    else:
                        self.STATUS = -13
                        return -13
                else:
                    if CONNECTION["OUT/IN"] not in HOSTSSUMMARY and CONNECTION["OUT/IN"] not in SWITCHESIDS and CONNECTION["OUT/IN"] not in OVSSWITCHESIDS:
                        self.STATUS = -13
                        return -13
            else:
                self.STATUS = -13
                return -13

            if CONNECTION["OUT/IN"] == CONNECTION["IN/OUT"]:
                self.STATUS = -14
                return -14

        self.CONNECTIONS = ConnectionsList
        return 0