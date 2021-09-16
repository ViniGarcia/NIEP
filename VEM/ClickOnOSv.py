from requests import get
from requests import post
from os import path
from json import loads

class ClickOnOSv:

    VNF_ADDRESS = ''
    VNF_CATALOG = {}


#__init__: gets the VNF instance management info and set the address
#          for REST requests.
    def __init__(self, managementVNF):

        self.VNF_ADDRESS = 'http://' + managementVNF + ":8000"
        self.VNF_CATALOG = {"GET_RUNNING": (self.getRunning, 0, "Check if an NF is running"),
                       "GET_FUNCTION": (self.getFunction, 0, "Check the NF installed"),
                       "GET_IDENTIFICATION": (self.getIdentification, 0, "Check the instaled NF ID"),
                       "GET_METRICS": (self.getMetrics, 0, "Check the VNF instance metrics"),
                       "GET_LOG": (self.getLog, 0, "Check the VNF instance log"),
                       "POST_START": (self.postStart, 0, "Start the NF execution"),
                       "POST_STOP": (self.postStop, 0, "Stop the NF execution"),
                       "POST_FUNCTION": (self.postFunction, 1, "Install an NF provided as path ($arg = NF path)")}

#getRunning: get request to check if a function is running in VNF.
    def getRunning(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/running')
        if response.status_code == 200:
            return (True, response.text)
        else:
            return (False,)

#getFunction: get the current function in the click file.
    def getFunction(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/read_file')
        if response.status_code == 200:
            return (True, response.text)
        else:
            return (False,)

#getIdentification: get the header of function in click file.
    def getIdentification(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/vnf_identification')
        if response.status_code == 200:
            return (True, response.text)
        else:
            return (False,)

#getMetrics: get VNF metrics such memory and cpu.
    def getMetrics(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/metrics')
        if response.status_code == 200:
            return (True, response.text)
        else:
            return (False,)

#getLog: get the VNF current log file content.
    def getLog(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/log')
        if response.status_code == 200:
            return (True, response.text)
        else:
            return (False,)

#postStart: start the function according to the click file.
    def postStart(self):

        if self.VNF_ADDRESS == '':
            return

        response = post(self.VNF_ADDRESS + '/click_plugin/start')
        if response.status_code == 200:
            return (True, str(response.status_code))
        else:
            return (False,)

#postStop: stop the function running.
    def postStop(self):

        if self.VNF_ADDRESS == '':
            return

        response = post(self.VNF_ADDRESS + '/click_plugin/stop')
        if response.status_code == 200:
            return (True, str(response.status_code))
        else:
            return (False,)

#postFunction: change the content of the click file according to the file path
#              received as argument, it must be a click function.
    def postFunction(self, functionPath):

        if self.VNF_ADDRESS == '':
            return

        if not path.isfile(functionPath):
            return (False, "File does not exist")

        functionFile = open(functionPath)
        functionData = functionFile.read()

        response = post(self.VNF_ADDRESS + '/click_plugin/write_file', params={'path':'func.click', 'content':functionData})
        if response.status_code == 200:
            return (True, str(response.status_code))
        else:
            return (False,)