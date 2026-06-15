import json
import random
from os import path

from ContainerNetworkRuntime import DEFAULT_CONTAINER_NETWORK_RUNTIME
from DockerRuntime import DEFAULT_DOCKER_RUNTIME


class Container:
    def __init__(self, configurationPath):
        self.ID = ''
        self.IMAGE = ''
        self.COMMAND = ['sleep', 'infinity']
        self.PRIVILEGED = True
        self.INTERFACES = []
        self.CONTAINER_STATUS = 0
        self.CONTAINER_JSON = ''
        self.CONTAINER = None
        self.RUNTIME = DEFAULT_DOCKER_RUNTIME
        self.NETWORK = DEFAULT_CONTAINER_NETWORK_RUNTIME

        self.inInterfaces(configurationPath)

    def __checkMAC(self, MAC):
        if isinstance(MAC, str) and len(MAC) == 17:
            for i in range(2, 16, 3):
                if MAC[i] != ':':
                    return -1
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
        if path.isfile(configurationPath):
            self.CONTAINER_JSON = configurationPath
            with open(self.CONTAINER_JSON) as dataContainer:
                parsedContainer = json.load(dataContainer)
        else:
            self.CONTAINER_STATUS = -1
            return -1

        if 'ID' in parsedContainer:
            self.ID = parsedContainer['ID']
        if 'IMAGE' in parsedContainer:
            self.IMAGE = parsedContainer['IMAGE']
        if 'COMMAND' in parsedContainer:
            self.COMMAND = parsedContainer['COMMAND']
        if 'PRIVILEGED' in parsedContainer:
            self.PRIVILEGED = parsedContainer['PRIVILEGED']
        if 'INTERFACES' in parsedContainer:
            self.INTERFACES = parsedContainer['INTERFACES']

        return self.fullValidation()

    def fullValidation(self):
        if self.ID == '':
            self.CONTAINER_STATUS = -1
            return -1
        if self.IMAGE == '':
            self.CONTAINER_STATUS = -2
            return -2
        if not isinstance(self.INTERFACES, list):
            self.CONTAINER_STATUS = -3
            return -3
        if not isinstance(self.COMMAND, (str, list)):
            self.CONTAINER_STATUS = -4
            return -4
        if not isinstance(self.PRIVILEGED, bool):
            self.CONTAINER_STATUS = -5
            return -5

        for iface in self.INTERFACES:
            if 'ID' not in iface or 'MAC' not in iface:
                self.CONTAINER_STATUS = -3
                return -3
            if self.__checkMAC(iface['MAC']):
                self.CONTAINER_STATUS = -3
                return -3
            if 'LINK_MAC' not in iface:
                iface['LINK_MAC'] = self.__randomizeMAC()

        self.CONTAINER_STATUS = 0
        return 0

    def createContainer(self):
        if self.CONTAINER_STATUS < 0:
            return
        self.RUNTIME.remove(self.ID)
        self.CONTAINER = self.RUNTIME.create(self.ID, self.IMAGE, self.COMMAND, self.PRIVILEGED)
        return 0

    def upContainer(self):
        if self.CONTAINER_STATUS < 0:
            return
        if self.CONTAINER is None:
            if not self.RUNTIME.exists(self.ID):
                create_status = self.createContainer()
                if create_status != 0:
                    return create_status
            self.CONTAINER = self.RUNTIME.lookup(self.ID)
        self.RUNTIME.start(self.CONTAINER)
        self.NETWORK.setup_interfaces(self.CONTAINER, self.INTERFACES)
        return 0

    def downContainer(self):
        if self.CONTAINER_STATUS < 0:
            return
        self.NETWORK.release_interfaces(self.INTERFACES)
        self.RUNTIME.remove(self.ID)
        self.CONTAINER = None
        return 0

    def execContainer(self, command):
        return self.RUNTIME.exec(self.ID, command)
