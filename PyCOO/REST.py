from requests import get
from requests import post
from os import path
from json import loads

class REST:

    VNF_ADDRESS = ''

#__init__: gets the VNF instance management info and set the address for RESTfull
#          requests.
    def __init__(self, managementVNF):

        self.VNF_ADDRESS = 'http://' + managementVNF

#getRunning: get request to check if a function is running in VNF.
#            [code, answer] ->
#               code - 200 if normal, other if error
#               answer - True or False
    def getRunning(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/running')
        return [str(response.status_code), response.text]

#getFunction: get the current function in the click file.
#            [code, answer] ->
#               code - 200 if normal, other if error
#               answer - file content.
    def getFunction(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/read_file')
        return [str(response.status_code), response.text]

#getIdentification: get the header of function in click file.
#            [code, answer] ->
#               code - 200 if normal, other if error
#               answer - file header data as a dictionary
    def getIdentification(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/vnf_identification')
        return [str(response.status_code), response.text]

#getMetrics: get VNF metrics such memory and cpu.
#            [code, answer] ->
#               code - 200 if normal, other if error
#               answer - VNF metrics as a dictionary
    def getMetrics(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/metrics')
        return [str(response.status_code), response.text]

#getLog: get the VNF current log file content.
#            [code, answer] ->
#               code - 200 if normal, other if error
#               answer - log file content.
    def getLog(self):

        if self.VNF_ADDRESS == '':
            return

        response = get(self.VNF_ADDRESS + '/click_plugin/log')
        return [str(response.status_code), response.text]

#postStart: start the function according to the click file.
#           code - 200 if normal, other if error
    def postStart(self):

        if self.VNF_ADDRESS == '':
            return

        response = post(self.VNF_ADDRESS + '/click_plugin/start')
        return response.status_code

#postStop: stop the function running.
#           code - 200 if normal, other if error
    def postStop(self):

        if self.VNF_ADDRESS == '':
            return

        response = post(self.VNF_ADDRESS + '/click_plugin/stop')
        return response.status_code

#postFunction: change the content of the click file according to the file path
#              received as argument, it must be a click function.
#              -1 - file does not exist
#              code - 200 if normal, other if error
    def postFunction(self, functionPath):

        if self.VNF_ADDRESS == '':
            return

        if not path.isfile(functionPath):
            return -1

        functionFile = open(functionPath)
        functionData = functionFile.read()

        response = post(self.VNF_ADDRESS + '/click_plugin/write_file?path=func.click&content=' + functionData)
        return response.status_code

# scriptError: trigger for a non 200 rest return.
#              -2 = replace file not found
#              -1 = script error routine executed with errors
#               0 = script error routine sucessfully executed
    def scriptError(self, scriptError, functionPath):

        for task in range(0, len(scriptError)):
            if scriptError[str(task + 1)] == 'start':
                resultCheck = self.postStart()
                if resultCheck != 200:
                    return -1
                continue
            if scriptError[str(task + 1)] == 'stop':
                resultCheck = self.postStop()
                if resultCheck != 200:
                    return -1
                continue
            if scriptError[str(task + 1)] == 'replace':
                if functionPath == None:
                    return -2
                resultCheck = self.postFunction(functionPath)
                if resultCheck != 200:
                    return -1
                continue
            if scriptError[str(task + 1)] == 'running':
                resultCheck = self.getRunning()
                if resultCheck[0] != '200':
                    return -1
                continue
            if scriptError[str(task + 1)] == 'data':
                resultCheck = self.getFunction()
                if resultCheck[0] != '200':
                    return -1
                continue
            if scriptError[str(task + 1)] == 'id':
                resultCheck = self.getIdentification()
                if resultCheck[0] != '200':
                    return -1
                continue
            if scriptError[str(task + 1)] == 'metrics':
                resultCheck = self.getMetrics()
                if resultCheck[0] != '200':
                    return -1
                continue
            if scriptError[str(task + 1)] == 'log':
                resultCheck = self.getLog()
                if resultCheck[0] != '200':
                    return -1
                continue
        return 0

#scriptExecution: execute defined tasks in a json script file.
#                 -6 = analog to -2 return from scriptError
#                 -5 = analog to -1 return from scriptError
#                 -4 = analog to 0 return from scriptError
#                 -3 = unhandled error
#                 -2 = required task not defined
#                 -1 = replace file not found
#                 [] = REST calls returns, status code and get actions response
    def scriptExecution(self, scriptTasks, scriptError, functionPath):

        tasksResults = []
        for task in range(0, len(scriptTasks)):
            if scriptTasks[str(task + 1)] == 'start':
                resultCheck = self.postStart()
                resultCheck = 404
                if resultCheck != 200:
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'stop':
                resultCheck = self.postStop()
                if resultCheck != 200:
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'replace':
                if functionPath == None:
                    return -1
                resultCheck = self.postFunction(functionPath)
                if resultCheck != 200:
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'running':
                resultCheck = self.getRunning()
                if resultCheck[0] != '200':
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'data':
                resultCheck = self.getFunction()
                if resultCheck[0] != '200':
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'id':
                resultCheck = self.getIdentification()
                if resultCheck[0] != '200':
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'metrics':
                resultCheck = self.getMetrics()
                if resultCheck[0] != '200':
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            if scriptTasks[str(task + 1)] == 'log':
                resultCheck = self.getLog()
                if resultCheck[0] != '200':
                    if scriptError != None:
                        return self.scriptError(scriptError, functionPath) - 4
                    else:
                        return -3
                tasksResults.append(resultCheck)
                continue

            return -2

        return tasksResults