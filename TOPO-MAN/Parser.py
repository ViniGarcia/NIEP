import json
from os.path import isfile
from sys import path
path.insert(0, '../VEM/')
from VNF import VNF
from SFC import SFC

class MNHost:
    ID = ""
    IP = None
    ELEM = None

    def __init__(self, ID, IP):
        self.ID = ID
        self.IP = IP

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class MNSwitch:
    ID = ""
    ELEM = None

    def __init__(self, ID):
        self.ID = ID

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

class MNController:
    ID = ""
    ELEM = None

    def __init__(self, ID):
        self.ID = ID

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
            SFCVNFS = self.SFCCheck()
            if isinstance(SFCVNFS, dict):
                if self.VNFSCheck(SFCVNFS) == 0:
                    if self.mininetCheck() == 0:
                        if self.connectionsCheck() == 0:
                            self.STATUS = 0

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

        MACMask = "FF:FF:FF:FF:FF:"
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

    def isint(self, s):
        try:
            int(s)
            return True
        except ValueError:
            return False

#------------------------------------------------------------------

    def VNFSCheck(self, SFCVNFS):

        FULLVNF = self.JSON['VNFS']
        for SFCID in SFCVNFS:
            for VNFPATH in SFCVNFS[SFCID]:
                if VNFPATH in FULLVNF:
                    FULLVNF.remove(VNFPATH)
            FULLVNF = FULLVNF + SFCVNFS[SFCID] 

        PATHINSTANCE = {}
        for VNFPATH in FULLVNF:
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

        for SFCINSTANCE in self.SFCS:
            SFCPATHS = [VNFPATH['PATH'] for VNFPATH in SFCINSTANCE.VNFS]
            for PATH in PATHINSTANCE:
                if PATH in SFCPATHS:
                    SFCINSTANCE.SFC_VNF_INSTANCES.append(PATHINSTANCE[PATH])
                    
        return 0

#------------------------------------------------------------------

    def SFCCheck(self):

        SFCVNFS = []
        SFCDIC = {}
        for SFCPATH in self.JSON['SFCS']:
            if isinstance(SFCPATH, basestring) and isfile(SFCPATH):
                instance = SFC(SFCPATH)
                if instance.SFC_STATUS < 0:
                    self.STATUS = -5
                    return -5
                self.SFCS.append(instance)
                for VNFPATH in instance.VNFS:
                    if VNFPATH not in self.VNFS:
                        SFCVNFS.append(VNFPATH["PATH"])
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
                    if "ID" in HOST and "IP" in HOST:
                        if HOST["ID"] in IDLIST:
                            self.STATUS = -7
                            return -7
                        else:
                            IDLIST.append(HOST["ID"])
                    else:
                        self.STATUS = -7
                        return -7

                    self.MNHOSTS.append(MNHost(HOST["ID"], HOST["IP"]))
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
                    if CONTROLLER in IDLIST:
                        self.STATUS = -9
                        return -9
                    else:
                        CONTROLLERLIST.append(CONTROLLER)

                    self.MNCONTROLLER.append(MNController(CONTROLLER))

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

        VNFSIDS = [VNFINSTANCE.ID for VNFINSTANCE in self.VNFS]
        HOSTSIDS = [HOST.ID for HOST in self.MNHOSTS]
        SWITCHESIDS = [SWITCH.ID for SWITCH in self.MNSWITCHES]
        OVSSWITCHESIDS = [OVS.ID for OVS in self.MNOVSES]

        if isinstance(self.JSON['CONNECTIONS'], list):
            ConnectionsList = self.JSON['CONNECTIONS']
        else:
            self.STATUS = -11
            return -11

        for CONNECTION in ConnectionsList:
            if "IN/OUT" in CONNECTION:
                if CONNECTION["IN/OUT"] in VNFSIDS:
                    if "IN/OUTIFACE" in CONNECTION:
                        if not any(CONNECTION["IN/OUTIFACE"] == IFACE["MAC"] for IFACE in self.VNFS[VNFSIDS.index(CONNECTION["IN/OUT"])].INTERFACES):
                            self.STATUS = -12
                            return -12
                    else:
                        self.STATUS = -12
                        return -12
                else:
                    if CONNECTION["IN/OUT"] not in HOSTSIDS and CONNECTION["IN/OUT"] not in SWITCHESIDS and CONNECTION["IN/OUT"] not in OVSSWITCHESIDS:
                        self.STATUS = -12
                        return -12
            else:
                self.STATUS = -12
                return -12

            if "OUT/IN" in CONNECTION:
                if CONNECTION["OUT/IN"] in VNFSIDS:
                    if "OUT/INIFACE" in CONNECTION:
                        if not any(CONNECTION["OUT/INIFACE"] == IFACE["MAC"] for IFACE in self.VNFS[VNFSIDS.index(CONNECTION["OUT/IN"])].INTERFACES):
                            self.STATUS = -13
                            return -13
                    else:
                        self.STATUS = -13
                        return -13
                else:
                    if CONNECTION["OUT/IN"] not in HOSTSIDS and CONNECTION["OUT/IN"] not in SWITCHESIDS and CONNECTION["OUT/IN"] not in OVSSWITCHESIDS:
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