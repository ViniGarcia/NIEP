import json
import random
import re
from ipaddress import ip_interface
from os import path

from niep.runtime.container_network import ContainerNetworkError, DEFAULT_CONTAINER_NETWORK_RUNTIME
from niep.runtime.docker import DEFAULT_DOCKER_RUNTIME, DockerRuntimeError


class Container:
    def __init__(self, configurationPath):
        self.ID = ''
        self.IMAGE = ''
        self.COMMAND = ['sleep', 'infinity']
        self.ENTRYPOINT = None
        self.PRIVILEGED = True
        self.SYSCTLS = {}
        self.INTERFACES = []
        self.CONTAINER_STATUS = 0
        self.DETAIL = ''
        self.CLEANUP_ERRORS = []
        self.CONTAINER_JSON = ''
        self.CONTAINER = None
        self.RUNTIME = DEFAULT_DOCKER_RUNTIME
        self.NETWORK = DEFAULT_CONTAINER_NETWORK_RUNTIME
        self._CLEANUP_COMPLETED = set()

        self.inInterfaces(configurationPath)

    def __checkMAC(self, MAC):
        if isinstance(MAC, str) and re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", MAC):
            return 0
        return -1

    def __randomizeMAC(self):
        values = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "a", "b", "c", "d", "e", "f"]
        mac = "02:"
        while True:
            mac = mac + values[random.randint(0, 15)] + values[random.randint(0, 15)]
            if len(mac) == 17:
                break
            mac = mac + ":"
        return mac

    def inInterfaces(self, configurationPath):
        if not path.isfile(configurationPath):
            self.CONTAINER_STATUS = -1
            self.DETAIL = "Container descriptor file does not exist: " + str(configurationPath)
            return -1

        self.CONTAINER_JSON = configurationPath
        try:
            with open(self.CONTAINER_JSON) as dataContainer:
                parsedContainer = json.load(dataContainer)
        except json.JSONDecodeError as exc:
            self.CONTAINER_STATUS = -1
            self.DETAIL = (
                "Invalid container JSON at line "
                + str(exc.lineno)
                + ", column "
                + str(exc.colno)
                + ": "
                + exc.msg
            )
            return -1
        except OSError as exc:
            self.CONTAINER_STATUS = -1
            self.DETAIL = "Could not read container descriptor: " + str(exc)
            return -1

        if not isinstance(parsedContainer, dict):
            self.CONTAINER_STATUS = -1
            self.DETAIL = "Container descriptor root must be a JSON object"
            return -1

        if 'ID' in parsedContainer:
            self.ID = parsedContainer['ID']
        if 'IMAGE' in parsedContainer:
            self.IMAGE = parsedContainer['IMAGE']
        if 'COMMAND' in parsedContainer:
            self.COMMAND = parsedContainer['COMMAND']
        if 'ENTRYPOINT' in parsedContainer:
            self.ENTRYPOINT = parsedContainer['ENTRYPOINT']
        if 'PRIVILEGED' in parsedContainer:
            self.PRIVILEGED = parsedContainer['PRIVILEGED']
        if 'SYSCTLS' in parsedContainer:
            self.SYSCTLS = parsedContainer['SYSCTLS']
        if 'INTERFACES' in parsedContainer:
            self.INTERFACES = parsedContainer['INTERFACES']

        return self.fullValidation()

    def fullValidation(self):
        if not isinstance(self.ID, str) or not self.ID:
            self.CONTAINER_STATUS = -1
            self.DETAIL = "Container field ID must be a non-empty string; value=" + repr(self.ID)
            return -1
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", self.ID):
            self.CONTAINER_STATUS = -1
            self.DETAIL = "Container field ID contains characters unsupported by Docker; value=" + repr(self.ID)
            return -1
        if not isinstance(self.IMAGE, str) or not self.IMAGE:
            self.CONTAINER_STATUS = -2
            self.DETAIL = "Container field IMAGE must be a non-empty string; value=" + repr(self.IMAGE)
            return -2
        if not isinstance(self.INTERFACES, list):
            self.CONTAINER_STATUS = -3
            self.DETAIL = "Container field INTERFACES must be a list; value=" + repr(self.INTERFACES)
            return -3
        if not isinstance(self.COMMAND, (str, list)):
            self.CONTAINER_STATUS = -4
            self.DETAIL = "Container field COMMAND must be a string or list; value=" + repr(self.COMMAND)
            return -4
        if isinstance(self.COMMAND, list) and not all(isinstance(item, str) for item in self.COMMAND):
            self.CONTAINER_STATUS = -4
            self.DETAIL = "Container COMMAND list must contain only strings; value=" + repr(self.COMMAND)
            return -4
        if self.ENTRYPOINT is not None and not isinstance(self.ENTRYPOINT, (str, list)):
            self.CONTAINER_STATUS = -4
            self.DETAIL = "Container field ENTRYPOINT must be null, a string or list; value=" + repr(self.ENTRYPOINT)
            return -4
        if isinstance(self.ENTRYPOINT, list) and not all(isinstance(item, str) for item in self.ENTRYPOINT):
            self.CONTAINER_STATUS = -4
            self.DETAIL = "Container ENTRYPOINT list must contain only strings; value=" + repr(self.ENTRYPOINT)
            return -4
        if not isinstance(self.PRIVILEGED, bool):
            self.CONTAINER_STATUS = -5
            self.DETAIL = "Container field PRIVILEGED must be boolean; value=" + repr(self.PRIVILEGED)
            return -5
        if not isinstance(self.SYSCTLS, dict):
            self.CONTAINER_STATUS = -6
            self.DETAIL = "Container field SYSCTLS must be a JSON object; value=" + repr(self.SYSCTLS)
            return -6
        for key, value in self.SYSCTLS.items():
            if not isinstance(key, str) or not key:
                self.CONTAINER_STATUS = -6
                self.DETAIL = "Container SYSCTLS keys must be non-empty strings; value=" + repr(key)
                return -6
            if not isinstance(value, (str, int, bool)):
                self.CONTAINER_STATUS = -6
                self.DETAIL = "Container SYSCTLS values must be strings, integers, or booleans; field=SYSCTLS." + key + "; value=" + repr(value)
                return -6
        self.SYSCTLS = {key: str(value).lower() if isinstance(value, bool) else str(value) for key, value in self.SYSCTLS.items()}

        interfaceIds = set()
        interfaceMacs = set()
        for index, iface in enumerate(self.INTERFACES):
            field = "INTERFACES[" + str(index) + "]"
            if not isinstance(iface, dict):
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + " must be a JSON object; value=" + repr(iface)
                return -3
            if 'ID' not in iface or 'MAC' not in iface:
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + " requires ID and MAC keys"
                return -3
            if not isinstance(iface['ID'], str) or not iface['ID']:
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + ".ID must be a non-empty string; value=" + repr(iface['ID'])
                return -3
            if len(iface['ID']) > 15:
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + ".ID exceeds the Linux interface name limit of 15 characters; value=" + repr(iface['ID'])
                return -3
            if iface['ID'] in interfaceIds:
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + ".ID is duplicated; value=" + repr(iface['ID'])
                return -3
            if self.__checkMAC(iface['MAC']):
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + ".MAC is invalid; value=" + repr(iface['MAC'])
                return -3
            if iface['MAC'].lower() in interfaceMacs:
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + ".MAC is duplicated; value=" + repr(iface['MAC'])
                return -3
            if iface.get('IP') is not None:
                if not isinstance(iface['IP'], str):
                    self.CONTAINER_STATUS = -3
                    self.DETAIL = field + ".IP must be null or a string; value=" + repr(iface['IP'])
                    return -3
                try:
                    ip_interface(iface['IP'])
                except ValueError:
                    self.CONTAINER_STATUS = -3
                    self.DETAIL = field + ".IP is not a valid IP address with prefix; value=" + repr(iface['IP'])
                    return -3
            if 'LINK_MAC' not in iface:
                iface['LINK_MAC'] = self.__randomizeMAC()
            elif self.__checkMAC(iface['LINK_MAC']):
                self.CONTAINER_STATUS = -3
                self.DETAIL = field + ".LINK_MAC is invalid; value=" + repr(iface['LINK_MAC'])
                return -3
            interfaceIds.add(iface['ID'])
            interfaceMacs.add(iface['MAC'].lower())

        self.CONTAINER_STATUS = 0
        self.DETAIL = ''
        return 0

    def createContainer(self):
        if self.CONTAINER_STATUS < 0:
            return self.CONTAINER_STATUS
        try:
            self.RUNTIME.remove(self.ID)
            self.CONTAINER = self.RUNTIME.create(
                self.ID,
                self.IMAGE,
                self.COMMAND,
                self.PRIVILEGED,
                self.ENTRYPOINT,
                self.SYSCTLS,
            )
        except DockerRuntimeError as exc:
            self.CONTAINER_STATUS = -10
            self.DETAIL = str(exc)
            return -10
        return 0

    def upContainer(self):
        if self.CONTAINER_STATUS < 0:
            return self.CONTAINER_STATUS
        # A new start is a new cleanup transaction.  Do not carry successful
        # operations from an earlier, fully or partially cleaned run into it.
        self._CLEANUP_COMPLETED = set()
        try:
            if self.CONTAINER is None:
                if not self.RUNTIME.exists(self.ID):
                    create_status = self.createContainer()
                    if create_status != 0:
                        return create_status
                self.CONTAINER = self.RUNTIME.lookup(self.ID)
            self.RUNTIME.start(self.CONTAINER)
            self.NETWORK.setup_interfaces(self.CONTAINER, self.INTERFACES)
        except (DockerRuntimeError, ContainerNetworkError) as exc:
            self.CONTAINER_STATUS = -10
            self.DETAIL = str(exc)
            self._rollback()
            return -10
        self.CONTAINER_STATUS = 0
        self.DETAIL = ''
        return 0

    def downContainer(self):
        return self.cleanupContainer()

    def cleanupContainer(self):
        errors = []
        cleanupErrors = []
        completed = getattr(self, '_CLEANUP_COMPLETED', None)
        if completed is None:
            completed = set()
            self._CLEANUP_COMPLETED = completed

        for interfaceIndex, interface in enumerate(self.INTERFACES):
            interfaceID = interface.get('ID', 'unknown')
            cleanupKey = ('veth_interface', str(interfaceID), interfaceIndex, 'release_interfaces')
            if cleanupKey in completed:
                continue
            try:
                status = self.NETWORK.release_interfaces([interface])
                if status not in (0, None):
                    raise RuntimeError(
                        "release_interfaces returned status " + str(status)
                    )
            except Exception as exc:
                errors.append(str(exc))
                cleanupErrors.append({
                    "resource_type": "veth_interface",
                    "resource_id": str(interfaceID),
                    "operation": "release_interfaces",
                    "message": str(exc),
                })
            else:
                completed.add(cleanupKey)

        removeKey = ('container', str(self.ID), 'remove')
        if removeKey not in completed:
            try:
                status = self.RUNTIME.remove(self.ID)
                if status not in (0, None):
                    raise RuntimeError("remove returned status " + str(status))
            except Exception as exc:
                errors.append(str(exc))
                cleanupErrors.append({
                    "resource_type": "container",
                    "resource_id": str(self.ID),
                    "operation": "remove",
                    "message": str(exc),
                })
            else:
                completed.add(removeKey)
        self.CONTAINER = None
        self.CLEANUP_ERRORS = cleanupErrors
        if errors:
            self.CONTAINER_STATUS = -10
            self.DETAIL = " | ".join(errors)
            return -10
        self.CONTAINER_STATUS = 0
        self.DETAIL = ''
        return 0

    def execContainer(self, command):
        return self.RUNTIME.exec(self.ID, command)

    def openShell(self, command):
        return self.RUNTIME.open_interactive_exec(self.ID, command)

    def _rollback(self):
        startupDetail = self.DETAIL
        cleanupStatus = self.cleanupContainer()
        cleanupDetail = self.DETAIL
        self.CONTAINER_STATUS = -10
        self.DETAIL = startupDetail
        if cleanupStatus != 0 and cleanupDetail:
            self.DETAIL += " | Rollback warnings: " + cleanupDetail
