############# WARNIGN #############
#THIS AGENT IS A PROTOTYPE, SO IT 
#WAS NOR TESTED NEITHER INCORPORED 
#TO THE NIEP CODE
###################################
import netifaces
from bottle import route, run, request
from json import loads, dumps
from ast import literal_eval
from subprocess import call, STDOUT
from os import devnull
from time import time
from sys import path
from socket import AF_INET
path.insert(0, '../TOPO-MAN/')
from Executer import Executer
from Parser import PlatformParser

#FNULL: redirects the system call normal output
FNULL = open(devnull, 'w')
#STDPATH: standard path - added to be used in NIEP
STDPATH = '../RVEM/'

class InstantiationPacket:
	FOLDER = None
	NIEPEXE = None
	JSON_DICT = {}

	#DOMAIN -> INP":"", "EGP":""
	#SFC -> "FILE":"", "DATA":""
	#VNFS -> "FILE":"DATA"

	def __init__(self, instantiationDict):
		self.JSON_DICT = instantiationDict

#------------------------------------------------------------------

	def create(self):

		if self.FOLDER != None:
			return -1

		self.FOLDER = str(int(time()))
		call(['mkdir', STDPATH + 'FILES/' + self.FOLDER], stdout=FNULL, stderr=STDOUT)
		
		adjustments = loads(self.JSON_DICT['SFC']['DATA'])
		for VNF in adjustments["VNFS"]:
			VNF["PATH"] = '../RVEM/FILES/' + self.FOLDER + '/' + VNF["PATH"]
		recordFile = open(STDPATH + 'FILES/' + self.FOLDER + '/' + self.JSON_DICT['SFC']['FILE'], "w")
		recordFile.write(dumps(adjustments))
		recordFile.close()

		for VNFFILE in self.JSON_DICT['VNFS']:
			recordFile = open(STDPATH + 'FILES/' + self.FOLDER + '/' + VNFFILE, "w")
			recordFile.write(self.JSON_DICT['VNFS'][VNFFILE])
			recordFile.close()

		recordFile = open(STDPATH + 'FILES/' + self.FOLDER + '/' + self.FOLDER + '.json', "w")
		recordFile.write('{\n\t"ID":"' + self.FOLDER +'",\n\t"VNFS":[],\n\t"SFCS":["../RVEM/FILES/' + self.FOLDER + '/' + self.JSON_DICT['SFC']['FILE'] + '"],')
		recordFile.write('\n\t"MININET":{\n\t\t"HOSTS":[],\n\t\t"SWITCHES":[],\n\t\t"CONTROLLERS":[],\n\t\t"OVSWITCHES":[]\n\t},')
		recordFile.write('\n\t"CONNECTIONS":[]\n}')
		recordFile.close()

		return 0

#------------------------------------------------------------------

	def instantiate(self):

		if self.NIEPEXE == None:
			self.NIEPEXE = Executer(PlatformParser(STDPATH + 'FILES/' + self.FOLDER + '/' + self.FOLDER + '.json'))
		if self.NIEPEXE.STATUS != None:
			return self.NIEPEXE.STATUS

		interfaceName = netifaces.gateways()['default'][AF_INET][1]
		call(['vconfig', 'add', interfaceName, self.JSON_DICT['DOMAIN']['IGP']], stdout=FNULL, stderr=STDOUT)
		call(['vconfig', 'add', interfaceName, self.JSON_DICT['DOMAIN']['EGP']], stdout=FNULL, stderr=STDOUT)

		call(['brctl', 'addbr', self.NIEPEXE.CONFIGURATION.SFCS[0].IP['LINK']], stdout=FNULL, stderr=STDOUT)
		call(['brctl', 'addif', self.NIEPEXE.CONFIGURATION.SFCS[0].IP['LINK'], interfaceName + '.' + self.JSON_DICT['DOMAIN']['IGP']], stdout=FNULL, stderr=STDOUT)
		call(['ifconfig', self.NIEPEXE.CONFIGURATION.SFCS[0].IP['LINK'], 'up'], stdout=FNULL, stderr=STDOUT)
		
		#TODO: All the egress points are sending data to the same vlan, in next it is necessary to think a strategy to change it
		for EP in self.NIEPEXE.CONFIGURATION.SFCS[0].OPS:
			call(['brctl', 'addbr', EP['LINK']], stdout=FNULL, stderr=STDOUT)
			call(['brctl', 'addif', EP['LINK'], interfaceName + '.' + self.JSON_DICT['DOMAIN']['EGP']], stdout=FNULL, stderr=STDOUT)
			call(['ifconfig', EP['LINK'], 'up'], stdout=FNULL, stderr=STDOUT)


		for VNFCONF in self.NIEPEXE.CONFIGURATION.SFCS[0].VNFS:
			splittedPath = VNFCONF['PATH'].split('/')
			fileName = splittedPath[len(splittedPath)-1]
			VNFCONF['PATH'] = STDPATH + "FILES/" + self.FOLDER + "/" + fileName

		self.NIEPEXE.topologyUp()
		if self.NIEPEXE.STATUS < 0:
			return -3

		return 0

#------------------------------------------------------------------

	def terminate(self):

		if self.NIEPEXE == None:
			return -1
		if self.NIEPEXE.STATUS < 0:
			return -2

		call(['virsh', 'net-destroy', 'vnNIEP'], stdout=FNULL, stderr=STDOUT)
		call(['ifconfig', 'vbrNIEP', 'down'], stdout=FNULL, stderr=STDOUT)
		call(['brctl', 'delbr', 'vbrNIEP'], stdout=FNULL, stderr=STDOUT)

		interfaceName = netifaces.gateways()['default'][AF_INET][1]
		call(['vconfig', 'rem', interfaceName + '.' + self.JSON_DICT['DOMAIN']['IGP']], stdout=FNULL, stderr=STDOUT)
		call(['vconfig', 'rem', interfaceName + '.' + self.JSON_DICT['DOMAIN']['EGP']], stdout=FNULL, stderr=STDOUT)

		self.NIEPEXE.topologyDown()

		return 0

#------------------------------------------------------------------

	def delete(self):
		
		if self.FOLDER == None:
			return -1

		self.terminate()
		call(['rm', '-r', STDPATH + 'FILES/' + self.FOLDER], stdout=FNULL, stderr=STDOUT)

		return 0

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

INSTANTIATION_DICT = None
INSTANTIATION_REQUEST = None
VNF_ACTIONS = {'start':'function_start', 
			'stop':'function_stop', 
			'replace':'function_replace', 
			'running':'function_run', 
			'data':'function_data', 
			'id':'function_id', 
			'metrics':'function_metrics', 
			'log':'function_log'}

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
#REMOTE SERVICE MANAGEMENT 

@route('/topology/creation/', method='POST')
def creationRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST != None:
		return '-1'

	INSTANTIATION_DICT = request.body.read()
	INSTANTIATION_REQUEST = InstantiationPacket(loads(INSTANTIATION_DICT))
	INSTANTIATION_REQUEST.create()
	return '0'

#------------------------------------------------------------------

@route('/topology/instantiation/', method='GET')
def instantiationRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'

	return str(INSTANTIATION_REQUEST.instantiate())

#------------------------------------------------------------------

@route('/topology/termination/', method='GET')
def terminationRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'

	return str(INSTANTIATION_REQUEST.terminate())

#------------------------------------------------------------------

@route('/topology/deletation/', method='GET')
def deletationRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.delete() == 0:
		INSTANTIATION_REQUEST = None
		INSTANTIATION_DICT = None
		return '0'
	return '-1'

#------------------------------------------------------------------

@route('/topology/data/', method='GET')
def dataRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	return INSTANTIATION_DICT

#------------------------------------------------------------------

@route('/topology/id/', method='GET')
def idRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	return INSTANTIATION_REQUEST.FOLDER

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
#REMOTE SFC MANAGEMENT

@route('/sfc/management/', method='GET')
def sfcmanagementRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	return str(INSTANTIATION_REQUEST.NIEPEXE.CONFIGURATION.SFCS[0].managementSFC())

#------------------------------------------------------------------

@route('/sfc/up/', method='GET')
def sfcupRequest():
	
	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	INSTANTIATION_REQUEST.NIEPEXE.CONFIGURATION.SFCS[0].checkStatusSFC()
	return str(INSTANTIATION_REQUEST.NIEPEXE.CONFIGURATION.SFCS[0].wakeSFC())

#------------------------------------------------------------------

@route('/sfc/down/', method='GET')
def sfcdownRequest():
	
	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	INSTANTIATION_REQUEST.NIEPEXE.CONFIGURATION.SFCS[0].checkStatusSFC()
	return str(INSTANTIATION_REQUEST.NIEPEXE.CONFIGURATION.SFCS[0].sleepSFC())

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
#REMOTE VNF MANAGEMENT

@route('/vnf/management/', method='POST')
def vnfmanagementRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	vnfID = request.body.read()
	if not vnfID in INSTANTIATION_REQUEST.NIEPEXE.VNFS:
		return 'None'

	return INSTANTIATION_REQUEST.NIEPEXE.VNFS[vnfID].managementVNF()

#------------------------------------------------------------------

@route('/vnf/up/', method='POST')
def vnfupRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	vnfID = request.body.read()
	if not vnfID in INSTANTIATION_REQUEST.NIEPEXE.VNFS:
		return 'None'

	return str(INSTANTIATION_REQUEST.NIEPEXE.VNFS[vnfID].upVNF())

#------------------------------------------------------------------

@route('/vnf/down/', method='POST')
def vnfdownRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	vnfID = request.body.read()
	if not vnfID in INSTANTIATION_REQUEST.NIEPEXE.VNFS:
		return 'None'

	return str(INSTANTIATION_REQUEST.NIEPEXE.VNFS[vnfID].sleepVNF())

#------------------------------------------------------------------

@route('/vnf/action/', method='POST')
def vnfactionRequest():

	global INSTANTIATION_DICT
	global INSTANTIATION_REQUEST
	global VNF_ACTIONS

	if INSTANTIATION_REQUEST == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE == None:
		return 'None'
	if INSTANTIATION_REQUEST.NIEPEXE.STATUS < 0:
		return 'None'

	actionData = literal_eval(request.body.read())
	if len(actionData) < 2:
		return 'None'
	if not actionData[0] in INSTANTIATION_REQUEST.NIEPEXE.VNFS:
		return 'None'
	if not actionData[1] in VNF_ACTIONS:
		return 'None'

	if actionData == 'replace':
		if len(actionData) < 3:
			return 'None'
		return str(INSTANTIATION_REQUEST.NIEPEXE.VNFS[actionData[0]].controlVNF('function_replace', [actionData[2]]))
	return str(INSTANTIATION_REQUEST.NIEPEXE.VNFS[actionData[0]].controlVNF(VNF_ACTIONS[actionData[1]], []))

#%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%

run(host='localhost', port=8152, debug=True)