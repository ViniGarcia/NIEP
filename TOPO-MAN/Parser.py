import re
import json
import random
from sys import path
from os.path import isabs, isfile, abspath, dirname, join, normpath

path.insert(0, '/'.join(abspath(__file__).split('/')[:-2] + ['VEM']))
from VNF import VNF
from SFC import SFC
from VM import VM
from Container import Container
from Spec import ConnectionSpec, ContainerSpec, InterfaceSpec, MininetControllerSpec, MininetHostSpec, MininetOVSSwitchSpec, MininetSwitchSpec, SFCSpec, TopologySpec, VMSpec, VNFSpec

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
# TO DO LIST

#Detect error when the same interface (MAC) is used to link multiple
#connections in CONNECTIONS of topology definitions.

#Detect the usage of VMs with alias, and block the usage of the VM
#original ID to other elements.

class PlatformParser:
    def __init__(self, jsonFilePath):
        self.SOURCE = abspath(jsonFilePath)
        self.JSON = None
        self.STATUS = None
        self.ID = ""
        self.VMS = []
        self.VNFS = []
        self.SFCS = []
        self.CONTAINERS = []
        self.VM_SPECS = []
        self.VNF_SPECS = []
        self.SFC_SPECS = []
        self.CONTAINER_SPECS = []
        self.MNHOSTS = []
        self.MNSWITCHES = []
        self.MNCONTROLLER = []
        self.MNOVSES = []
        self.CONNECTIONS = []
        self.DETAIL = ""
        self.ERROR = None
        self.SPEC = None
        self.BASE_DIR = dirname(abspath(jsonFilePath))

        if not isfile(jsonFilePath):
            self.fail(-1, "Topology file does not exist", file=self.SOURCE)
            return

        try:
            with open(jsonFilePath) as data:
                self.JSON = json.load(data)
        except json.JSONDecodeError as exc:
            self.fail(
                -1,
                "Invalid JSON syntax at line " + str(exc.lineno) + ", column " + str(exc.colno) + ": " + exc.msg,
                file=self.SOURCE,
            )
            return
        except OSError as exc:
            self.fail(-1, "Could not read topology file: " + str(exc), file=self.SOURCE)
            return

        if not isinstance(self.JSON, dict):
            self.fail(-2, "Topology root must be a JSON object", field="$", value=self.JSON)
            return

        for requiredKey in ('ID', 'VMS', 'VNFS', 'SFCS', 'MININET', 'CONNECTIONS'):
            if requiredKey not in self.JSON:
                self.fail(-1, "Missing required key", field=requiredKey)
                return
        if 'CONTAINERS' not in self.JSON:
            self.JSON['CONTAINERS'] = []

        if isinstance(self.JSON['ID'], str):
            self.ID = self.JSON['ID']
        else:
            self.fail(-2, "Expected a string", field="ID", value=self.JSON['ID'])
            return

        for listKey in ('VMS', 'VNFS', 'SFCS', 'CONTAINERS'):
            if not isinstance(self.JSON[listKey], list):
                self.fail(-2, "Expected a list", field=listKey, value=self.JSON[listKey])
                return

        if not isinstance(self.JSON['MININET'], dict):
            self.fail(-6, "Expected a JSON object", field="MININET", value=self.JSON['MININET'])
            return
        if not isinstance(self.JSON['CONNECTIONS'], list):
            self.fail(-11, "Expected a list", field="CONNECTIONS", value=self.JSON['CONNECTIONS'])
            return

        if self.STATUS == None:
            if self.VMSCheck() == 0:
                if self.CONTAINERSCheck() == 0:
                    SFCVNFS = self.SFCCheck()
                    if isinstance(SFCVNFS, dict):
                        if self.VNFSCheck(SFCVNFS) == 0:
                            if self.mininetCheck() == 0:
                                if self.resourceIdentityCheck() == 0 and self.connectionsCheck() == 0:
                                    self.SPEC = TopologySpec(
                                        id=self.ID,
                                        vms=self.VM_SPECS,
                                        vnfs=self.VNF_SPECS,
                                        sfcs=self.SFC_SPECS,
                                        containers=self.CONTAINER_SPECS,
                                        mininet_hosts=self.MNHOSTS,
                                        mininet_switches=self.MNSWITCHES,
                                        mininet_controllers=self.MNCONTROLLER,
                                        mininet_ovs_switches=self.MNOVSES,
                                        connections=self.CONNECTIONS,
                                    )
                                    self.STATUS = 0

#------------------------------------------------------------------

    def fail(self, status, message, field=None, value=None, file=None):
        parts = [message]
        if field is not None:
            parts.append("field=" + str(field))
        if value is not None:
            parts.append("value=" + repr(value))
        if file is not None:
            parts.append("file=" + str(file))
        self.STATUS = status
        self.DETAIL = "; ".join(parts)
        self.ERROR = {
            "message": message,
            "field": field,
            "value": value,
            "file": file or self.SOURCE,
        }
        return status

#------------------------------------------------------------------

    def checkIP(self, IP):

        if isinstance(IP, str) and re.match("^([01]?\\d\\d?|2[0-4]\\d|25[0-5])(?:\\.[01]?\\d\\d?|\\.2[0-4]\\d|\\.25[0-5]){3}(?:/[0-2]\\d|/3[0-2])?$", IP):
            return 0

        return -1

#------------------------------------------------------------------

    def checkMAC(self, MAC):

        if isinstance(MAC, str) and re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", MAC):
            return 0
        return -1

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
        except (TypeError, ValueError):
            return False

#------------------------------------------------------------------

    def resolvePath(self, filePath):
        if not isinstance(filePath, str):
            return filePath
        if isfile(filePath):
            return filePath
        if isabs(filePath):
            return filePath
        return normpath(join(self.BASE_DIR, filePath))

#------------------------------------------------------------------
#TODO [VINICIUS - 30/08/21]: Add security tests to duplicate IDs (will raise a KVM error if an ID is duplicated)

    def VMSCheck(self):

        for index, originalPath in enumerate(self.JSON['VMS']):
            field = "VMS[" + str(index) + "]"
            if not isinstance(originalPath, str):
                return self.fail(-2, "VM descriptor path must be a string", field=field, value=originalPath)
            vmPath = self.resolvePath(originalPath)
            if not isfile(vmPath):
                return self.fail(-2, "VM descriptor file does not exist", field=field, value=originalPath, file=vmPath)
            try:
                instance = VM(vmPath, None, None)
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
                return self.fail(-3, "Could not parse VM descriptor: " + str(exc), field=field, file=vmPath)
            if instance.VM_STATUS < 0:
                return self.fail(
                    -3,
                    "VM descriptor failed validation (VM_STATUS=" + str(instance.VM_STATUS) + ")",
                    field=field,
                    file=vmPath,
                )
            self.VMS.append(instance)
            self.VM_SPECS.append(VMSpec.from_vm(instance))

        return 0

#------------------------------------------------------------------

    def CONTAINERSCheck(self):

        for index, originalPath in enumerate(self.JSON['CONTAINERS']):
            field = "CONTAINERS[" + str(index) + "]"
            if not isinstance(originalPath, str):
                return self.fail(-2, "Container descriptor path must be a string", field=field, value=originalPath)
            containerPath = self.resolvePath(originalPath)
            if not isfile(containerPath):
                return self.fail(-2, "Container descriptor file does not exist", field=field, value=originalPath, file=containerPath)
            try:
                instance = Container(containerPath)
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
                return self.fail(-3, "Could not parse container descriptor: " + str(exc), field=field, file=containerPath)
            if instance.CONTAINER_STATUS < 0:
                detail = getattr(instance, 'DETAIL', '') or (
                    "Container descriptor failed validation (CONTAINER_STATUS="
                    + str(instance.CONTAINER_STATUS) + ")"
                )
                return self.fail(-3, detail, field=field, file=containerPath)
            self.CONTAINERS.append(instance)
            self.CONTAINER_SPECS.append(ContainerSpec.from_container(instance))

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
        for index, originalPath in enumerate(self.JSON['VNFS']):
            field = "VNFS[" + str(index) + "]"
            if not isinstance(originalPath, str):
                return self.fail(-2, "VNF descriptor path must be a string", field=field, value=originalPath)
            vnfPath = self.resolvePath(originalPath)
            if not isfile(vnfPath):
                return self.fail(-2, "VNF descriptor file does not exist", field=field, value=originalPath, file=vnfPath)
            try:
                instance = VNF(vnfPath, None)
            except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
                return self.fail(-3, "Could not parse VNF descriptor: " + str(exc), field=field, file=vnfPath)
            if instance.VNF_STATUS < 0:
                vm = getattr(instance, 'VM', None)
                return self.fail(
                    -3,
                    "VNF descriptor failed validation: VNF_STATUS="
                    + str(instance.VNF_STATUS)
                    + ", VM_STATUS="
                    + str(getattr(vm, 'VM_STATUS', None)),
                    field=field,
                    file=vnfPath,
                )
            self.VNFS.append(instance)
            self.VNF_SPECS.append(VNFSpec.from_vnf(instance))
            PATHINSTANCE[vnfPath] = instance

        for originalPath, connections in VERIFIEDSFCVNFS.items():
            vnfPath = self.resolvePath(originalPath)
            if isfile(vnfPath):
                try:
                    instance = VNF(vnfPath, connections)
                except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
                    return self.fail(-3, "Could not parse SFC VNF descriptor: " + str(exc), file=vnfPath)
                if instance.VNF_STATUS < 0:
                    vm = getattr(instance, 'VM', None)
                    return self.fail(
                        -3,
                        "SFC VNF failed validation: VNF_STATUS="
                        + str(instance.VNF_STATUS)
                        + ", VM_STATUS="
                        + str(getattr(vm, 'VM_STATUS', None)),
                        file=vnfPath,
                    )
                self.VNFS.append(instance)
                self.VNF_SPECS.append(VNFSpec.from_vnf(instance))
                PATHINSTANCE[vnfPath] = instance
            else:
                return self.fail(-2, "SFC VNF descriptor file does not exist", file=vnfPath)


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
        for index, originalPath in enumerate(self.JSON['SFCS']):
            field = "SFCS[" + str(index) + "]"
            if not isinstance(originalPath, str):
                return self.fail(-4, "SFC descriptor path must be a string", field=field, value=originalPath)
            sfcPath = self.resolvePath(originalPath)
            if isfile(sfcPath):
                try:
                    instance = SFC(sfcPath)
                except (json.JSONDecodeError, OSError, KeyError, TypeError, ValueError) as exc:
                    return self.fail(-5, "Could not parse SFC descriptor: " + str(exc), field=field, file=sfcPath)
                if instance.SFC_STATUS < 0:
                    return self.fail(
                        -5,
                        "SFC descriptor failed validation (SFC_STATUS=" + str(instance.SFC_STATUS) + ")",
                        field=field,
                        file=sfcPath,
                    )
                if instance.prepareSFC() < 0:
                    return self.fail(
                        -5,
                        "SFC preparation failed (SFC_STATUS=" + str(instance.SFC_STATUS) + ")",
                        field=field,
                        file=sfcPath,
                    )
                self.SFCS.append(instance)
                self.SFC_SPECS.append(SFCSpec.from_sfc(instance))

                for VNFCONF in instance.SFC_VNFS_CONF:
                    if VNFCONF[0][0] not in SFCVNFS:                                                    #VNF REDEFINITION, FIRST ASSUMED
                        SFCVNFS[VNFCONF[0][0]] = {"PATH":VNFCONF[0][1], "CONNECTIONS":VNFCONF[1:]}
                    else:
                        return self.fail(-5, "Duplicate VNF ID inside SFC", field=field, value=VNFCONF[0][0], file=sfcPath)
                SFCDIC[instance.ID] = SFCVNFS
                SFCVNFS = []
            else:
                return self.fail(-4, "SFC descriptor file does not exist", field=field, value=originalPath, file=sfcPath)

        return SFCDIC

#------------------------------------------------------------------

    def mininetCheck(self):

        MininetList = self.JSON['MININET']

        IDLIST = ['UNICTRL']
        CONTROLLERLIST = []
        for key in ("HOSTS", "SWITCHES", "CONTROLLERS", "OVSWITCHES"):
            if key not in MininetList:
                return self.fail(-6, "Missing required Mininet key", field="MININET." + key)
            if not isinstance(MininetList[key], list):
                return self.fail(-6, "Expected a list", field="MININET." + key, value=MininetList[key])

        for hostIndex, host in enumerate(MininetList["HOSTS"]):
            hostField = "MININET.HOSTS[" + str(hostIndex) + "]"
            if not isinstance(host, dict):
                return self.fail(-7, "Host must be a JSON object", field=hostField, value=host)
            for key in ("ID", "INTERFACES"):
                if key not in host:
                    return self.fail(-7, "Missing required host key", field=hostField + "." + key)
            if not isinstance(host["ID"], str) or not host["ID"]:
                return self.fail(-7, "Host ID must be a non-empty string", field=hostField + ".ID", value=host["ID"])
            if host["ID"] in IDLIST:
                return self.fail(-7, "Duplicate topology node ID", field=hostField + ".ID", value=host["ID"])
            if not isinstance(host["INTERFACES"], list):
                return self.fail(-7, "Host interfaces must be a list", field=hostField + ".INTERFACES", value=host["INTERFACES"])

            for ifaceIndex, iface in enumerate(host["INTERFACES"]):
                ifaceField = hostField + ".INTERFACES[" + str(ifaceIndex) + "]"
                if not isinstance(iface, dict):
                    return self.fail(-7, "Interface must be a JSON object", field=ifaceField, value=iface)
                for key in ("MAC", "IP"):
                    if key not in iface:
                        return self.fail(-7, "Missing required interface key", field=ifaceField + "." + key)
                if self.checkMAC(iface["MAC"]):
                    return self.fail(-7, "Invalid MAC address", field=ifaceField + ".MAC", value=iface["MAC"])
                if iface["IP"] is not None and self.checkIP(iface["IP"]):
                    return self.fail(-7, "Invalid IPv4 address or prefix", field=ifaceField + ".IP", value=iface["IP"])

            IDLIST.append(host["ID"])
            interfaces = [InterfaceSpec.from_dict(iface) for iface in host["INTERFACES"]]
            self.MNHOSTS.append(MininetHostSpec(host["ID"], interfaces))

        for switchIndex, switch in enumerate(MininetList["SWITCHES"]):
            field = "MININET.SWITCHES[" + str(switchIndex) + "]"
            if not isinstance(switch, str) or not switch:
                return self.fail(-8, "Switch ID must be a non-empty string", field=field, value=switch)
            if switch in IDLIST:
                return self.fail(-8, "Duplicate topology node ID", field=field, value=switch)
            IDLIST.append(switch)
            self.MNSWITCHES.append(MininetSwitchSpec(switch))

        for controllerIndex, controller in enumerate(MininetList["CONTROLLERS"]):
            field = "MININET.CONTROLLERS[" + str(controllerIndex) + "]"
            if not isinstance(controller, dict):
                return self.fail(-9, "Controller must be a JSON object", field=field, value=controller)
            for key in ("ID", "IP", "PORT"):
                if key not in controller:
                    return self.fail(-9, "Missing required controller key", field=field + "." + key)
            if not isinstance(controller["ID"], str) or not controller["ID"]:
                return self.fail(-9, "Controller ID must be a non-empty string", field=field + ".ID", value=controller["ID"])
            if controller["ID"] in IDLIST or controller["ID"] in CONTROLLERLIST:
                return self.fail(-9, "Duplicate topology node ID", field=field + ".ID", value=controller["ID"])
            if self.checkIP(controller["IP"]):
                return self.fail(-9, "Invalid controller IPv4 address", field=field + ".IP", value=controller["IP"])
            if not self.isint(controller["PORT"]):
                return self.fail(-9, "Controller port must be an integer", field=field + ".PORT", value=controller["PORT"])
            port = int(controller["PORT"])
            if port < 1 or port > 65535:
                return self.fail(-9, "Controller port must be between 1 and 65535", field=field + ".PORT", value=port)
            CONTROLLERLIST.append(controller["ID"])
            self.MNCONTROLLER.append(MininetControllerSpec(controller["ID"], controller["IP"], port))

        for ovsIndex, ovsSwitch in enumerate(MininetList["OVSWITCHES"]):
            field = "MININET.OVSWITCHES[" + str(ovsIndex) + "]"
            if not isinstance(ovsSwitch, dict):
                return self.fail(-10, "OVS switch must be a JSON object", field=field, value=ovsSwitch)
            for key in ("ID", "CONTROLLER"):
                if key not in ovsSwitch:
                    return self.fail(-10, "Missing required OVS switch key", field=field + "." + key)
            if not isinstance(ovsSwitch["ID"], str) or not ovsSwitch["ID"]:
                return self.fail(-10, "OVS switch ID must be a non-empty string", field=field + ".ID", value=ovsSwitch["ID"])
            if ovsSwitch["ID"] in IDLIST or ovsSwitch["ID"] in CONTROLLERLIST:
                return self.fail(-10, "Duplicate topology node ID", field=field + ".ID", value=ovsSwitch["ID"])
            if ovsSwitch["CONTROLLER"] not in CONTROLLERLIST:
                return self.fail(
                    -10,
                    "OVS switch references an unknown controller",
                    field=field + ".CONTROLLER",
                    value=ovsSwitch["CONTROLLER"],
                )
            IDLIST.append(ovsSwitch["ID"])
            self.MNOVSES.append(MininetOVSSwitchSpec(ovsSwitch["ID"], ovsSwitch["CONTROLLER"]))

        return 0

# ------------------------------------------------------------------

    def resourceIdentityCheck(self):
        resources = []
        resources.extend(("VM", vm.ID) for vm in self.VMS)
        resources.extend(("container", container.ID) for container in self.CONTAINERS)
        resources.extend(("VNF", vnf.ID) for vnf in self.VNFS)
        resources.extend(("Mininet host", host.ID) for host in self.MNHOSTS)
        resources.extend(("Mininet switch", switch.ID) for switch in self.MNSWITCHES)
        resources.extend(("Mininet controller", controller.ID) for controller in self.MNCONTROLLER)
        resources.extend(("Mininet OVS switch", ovs.ID) for ovs in self.MNOVSES)

        owners = {}
        for resourceType, resourceId in resources:
            if resourceId in owners:
                return self.fail(
                    -11,
                    "Duplicate resource ID shared by "
                    + owners[resourceId]
                    + " and "
                    + resourceType,
                    field="ID",
                    value=resourceId,
                )
            owners[resourceId] = resourceType

        interfaceOwners = {}
        for resourceType, resource in (
            [("VM", item) for item in self.VMS]
            + [("container", item) for item in self.CONTAINERS]
            + [("VNF", item.VM) for item in self.VNFS]
        ):
            for iface in resource.INTERFACES:
                interfaceId = iface.get("ID")
                if interfaceId in interfaceOwners:
                    return self.fail(
                        -11,
                        "Duplicate external interface ID shared by "
                        + interfaceOwners[interfaceId]
                        + " and "
                        + resourceType,
                        field="INTERFACES.ID",
                        value=interfaceId,
                    )
                interfaceOwners[interfaceId] = resourceType
        return 0

# ------------------------------------------------------------------

    def connectionsCheck(self):

        VMSSUMMARY = {VMINSTANCE.ID:VMINSTANCE for VMINSTANCE in self.VMS}
        for CONTAINERINSTANCE in self.CONTAINERS:
            VMSSUMMARY[CONTAINERINSTANCE.ID] = CONTAINERINSTANCE
        HOSTSSUMMARY = {HOSTINSTANCE.ID:HOSTINSTANCE for HOSTINSTANCE in self.MNHOSTS}
        for VNFINSTANCE in self.VNFS:
            VMSSUMMARY[VNFINSTANCE.ID] = VNFINSTANCE.VM
        SWITCHESIDS = [SWITCH.ID for SWITCH in self.MNSWITCHES]
        OVSSWITCHESIDS = [OVS.ID for OVS in self.MNOVSES]

        ConnectionsList = self.JSON['CONNECTIONS']
        endpoints = {}
        endpoints.update(VMSSUMMARY)
        endpoints.update(HOSTSSUMMARY)
        networkNodes = set(SWITCHESIDS + OVSSWITCHESIDS)
        usedInterfaces = set()

        for connectionIndex, connection in enumerate(ConnectionsList):
            field = "CONNECTIONS[" + str(connectionIndex) + "]"
            if not isinstance(connection, dict):
                return self.fail(-11, "Connection must be a JSON object", field=field, value=connection)

            for endpointKey, ifaceKey, status in (
                ("IN/OUT", "IN/OUTIFACE", -12),
                ("OUT/IN", "OUT/INIFACE", -13),
            ):
                endpointField = field + "." + endpointKey
                if endpointKey not in connection:
                    return self.fail(status, "Missing connection endpoint", field=endpointField)
                endpointId = connection[endpointKey]
                if not isinstance(endpointId, str) or not endpointId:
                    return self.fail(status, "Connection endpoint must be a non-empty string", field=endpointField, value=endpointId)
                if endpointId not in endpoints and endpointId not in networkNodes:
                    return self.fail(status, "Connection references an unknown endpoint", field=endpointField, value=endpointId)
                if endpointId in endpoints:
                    ifaceField = field + "." + ifaceKey
                    if ifaceKey not in connection:
                        return self.fail(status, "External endpoint requires an interface MAC", field=ifaceField)
                    ifaceMac = connection[ifaceKey]
                    availableMacs = [iface["MAC"] for iface in endpoints[endpointId].INTERFACES]
                    if ifaceMac not in availableMacs:
                        return self.fail(
                            status,
                            "Interface MAC does not belong to endpoint "
                            + endpointId
                            + "; available="
                            + repr(availableMacs),
                            field=ifaceField,
                            value=ifaceMac,
                        )
                    interfaceKey = (endpointId, ifaceMac.lower())
                    if interfaceKey in usedInterfaces:
                        return self.fail(
                            -11,
                            "External interface is used by more than one connection",
                            field=ifaceField,
                            value=ifaceMac,
                        )
                    usedInterfaces.add(interfaceKey)

            if connection["OUT/IN"] == connection["IN/OUT"]:
                return self.fail(
                    -14,
                    "A connection cannot link an endpoint to itself",
                    field=field,
                    value=connection["IN/OUT"],
                )

        self.CONNECTIONS = [ConnectionSpec.from_dict(CONNECTION) for CONNECTION in ConnectionsList]
        return 0
