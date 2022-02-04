import multiprocessing
import requests
import bottle
import math
import yaml
import sys
import re

import NSH
import NM

################################################### SC AREA ###################################################
class SC:

	__default_port = 12000
	__default_sc_ip = None
	__default_net_ip = None

	neighbor_sc_addresses = None
	neighbor_sc_majority = None

	sff_addresses = None
	sfp_sffs = None
	sfp_routing = None
	sfp_destinations = None

	nsh_processor = None

	data_manager = None
	data_queue = None
	data_mutex = None
	data_semaphore = None

	ft_manager = None
	clients_manager = None

	processing_server = None
	

	def __init__(self, interface_net_inc_ip, interface_sc_access_ip, neighbor_sc_addresses):

		self.__default_net_ip = interface_net_inc_ip
		self.__default_sc_ip = interface_sc_access_ip

		self.neighbor_sc_addresses = neighbor_sc_addresses
		self.neighbor_sc_majority = math.ceil((len(neighbor_sc_addresses) + 1) / 2 + 0.1)

		self.sff_addresses = {}
		self.sfp_sffs = {}
		self.sfp_routing = {}
		self.sfp_destinations = {}

		self.nsh_processor = NSH.NSH()

		self.data_manager = multiprocessing.Manager()
		self.data_queue = self.data_manager.list()
		self.data_mutex = self.data_manager.Lock()
		self.data_semaphore = self.data_manager.Semaphore(0)

		self.ft_manager = NM.NET_MANAGER(self.__default_sc_ip, self.data_queue, self.data_mutex, self.data_semaphore, False)
		self.clients_manager = NM.NET_MANAGER(self.__default_net_ip, self.data_queue, self.data_mutex, self.data_semaphore, False)

		self.clients_manager.startServer()
		self.ft_manager.startServer()


	def __isIP(self, potential_ip):

		return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())


	def shutdownSC(self):

		if self.ft_manager != None:
			self.ft_manager.shutdownManager()

		if self.clients_manager != None:
			self.clients_manager.shutdownManager()

		self.data_mutex.acquire()

		if self.processing_server != None:
			self.processing_server.terminate()


	def registerSFF(self, sff_id, sff_address):

		if not isinstance(sff_id, int):
			return -1
		if not isinstance(sff_address, str):
			return -2

		if not self.__isIP(sff_address):
			return -3

		self.sff_addresses[sff_id] = sff_address
		return 0


	def deleteSFP(self, sfp_id, sff_configure):

		try:
			sfp_id = int(sfp_id)
		except:
			return -1

		res_code = 0

		for destination in list(self.sfp_destinations.keys()):
			if self.sfp_destinations[destination] == sfp_id:
				self.sfp_destinations.pop(destination)

		if sfp_id in self.sfp_routing:
			self.sfp_routing.pop(sfp_id)

		if sfp_id in self.sfp_sffs:
			if sff_configure:
				for sff in self.sfp_sffs[sfp_id]:
					reg_result = requests.post("http://" + self.sff_addresses[sff] + ":8080/delete", {"service_path":sfp_id})
					if reg_result.status_code != 200:
						res_code = -2
			self.sfp_sffs.pop(sfp_id)

		return res_code


	def registerSFP(self, sfp_id, sf_addresses, sf_mapping, sfp_routing, sfp_destinations, sff_configure):

		if not isinstance(sfp_id, int):
			return -1
		if not isinstance(sf_addresses, dict):
			return -2
		if not isinstance(sf_mapping, dict):
			return -3
		if not isinstance(sfp_routing, dict):
			return -4
		if not isinstance(sfp_destinations, list):
			return -5

		if len(sf_addresses.keys()) == 0:
			return -6
		if list(range(1, len(sf_addresses.keys()) + 1)) != list(sf_addresses.keys()):
			return -7

		for sf in sf_addresses:
			for instance in sf_addresses[sf]:
				if not isinstance(instance, str):
					return -8
				if not self.__isIP(instance):
					return -9
			if not sf in sf_mapping:
				return -10

		if len(sf_mapping.keys()) == 0:
			return -11
		for sf in sf_mapping:
			if not isinstance(sf_mapping[sf], list):
				return -12
			if not sf in sf_addresses:
				return -13
			for sff in sf_mapping[sf]:	
				if not sff in self.sff_addresses:
					return -14

		if list(sf_addresses.keys()) != list(sfp_routing.keys()):
			return -15
		for route in sfp_routing:
			if not sfp_routing[route] in sf_addresses and sfp_routing[route] != None:
				return -16

		for destination in sfp_destinations:
			if not isinstance(destination, str):
				return -17
			if not self.__isIP(destination):
				return -18

		if sfp_id in self.sfp_routing:
			self.deleteSFP(sfp_id, sff_configure)

		for sf in sf_mapping[1]:
			reg_result = requests.post("http://" + self.sff_addresses[sf] + ":8080/entity", {"service_path":sfp_id, "service_index":0, "ip_address":self.__default_sc_ip})		
			if reg_result.status_code != 200:
				return -19

		if sff_configure:
			none_si = max([si for si in list(sfp_routing.values()) + list(sfp_routing.keys()) if si != None]) + 1
			for none_key in [key for (key, value) in sfp_routing.items() if value == None]:
				sfp_routing[none_key] = none_si
				for sff in sf_mapping[none_key]:
					reg_result = requests.post("http://" + self.sff_addresses[sff] + ":8080/entity", {"service_path":sfp_id, "service_index":none_si, "ip_address":None})
					if reg_result.status_code != 200:
						return -19

			for sf in sf_addresses:
				for sff in sf_mapping[sf]:
					for instance in sf_addresses[sf]:
						reg_result = requests.post("http://" + self.sff_addresses[sff] + ":8080/entity", {"service_path":sfp_id, "service_index":sf, "ip_address":instance})
						if reg_result.status_code != 200:
							return -19

					if sfp_routing[sf] != none_si:
						if not sff in sf_mapping[sfp_routing[sf]]:
							reg_result = requests.post("http://" + self.sff_addresses[sff] + ":8080/entity", {"service_path":sfp_id, "service_index":sfp_routing[sf], "ip_address":self.sff_addresses[sff_route]})		
							if reg_result.status_code != 200:
								return -19
							reg_result = requests.post("http://" + self.sff_addresses[sff_route] + ":8080/entity", {"service_path":sfp_id, "service_index":sf, "ip_address":self.sff_addresses[sff]})		
							if reg_result.status_code != 200:
								return -19

			for sff in sf_mapping[1]:
				reg_result = requests.post("http://" + self.sff_addresses[sff] + ":8080/route", {"service_path":sfp_id, "service_index":0, "next_destination":1})		
				if reg_result.status_code != 200:
					return -20

			for sf in sfp_routing:
				for sff in sf_mapping[sf]:
					reg_result = requests.post("http://" + self.sff_addresses[sff] + ":8080/route", {"service_path":sfp_id, "service_index":sf, "next_destination":sfp_routing[sf]})		
					if reg_result.status_code != 200:
						return -20

					if sfp_routing[sf] != none_si:
						for sff_route in sf_mapping[sfp_routing[sf]]:
							if sff != sff_route:
								reg_result = requests.post("http://" + self.sff_addresses[sff_route] + ":8080/route", {"service_path":sfp_id, "service_index":sf, "next_destination":sfp_routing[sf]})
								if reg_result.status_code != 200:
									return -20


		self.sfp_sffs[sfp_id] = list(set(sum(sf_mapping.values(), [])))
		self.sfp_routing[sfp_id] = sf_mapping[list(sfp_routing.keys())[0]]

		for destination in sfp_destinations:
			self.sfp_destinations[destination] = sfp_id

		return 0

	def setupSFP(self, sfp_yaml, sff_configure):
		
		try:
			sfp_data = yaml.safe_load(sfp_yaml)
		except:
			return (-1,)

		if not "id" in sfp_data:
			return (-2,)
		if not "sf" in sfp_data:
			return (-3,)
		if not "sff" in sfp_data:
			return (-4,)
		if not "sf_sff" in sfp_data:
			return (-5,)
		if not "sfp" in sfp_data:
			return (-6,)
		if not "sfp_destinations" in sfp_data:
			return (-7,)
		if not isinstance(sff_configure, bool):
			return (-8,)

		for sff in sfp_data["sff"]:
			reg_result = self.registerSFF(sff, sfp_data["sff"][sff])
			if reg_result != 0:
				return (-9, reg_result) 

		reg_result = self.registerSFP(sfp_data["id"], sfp_data["sf"], sfp_data["sf_sff"], sfp_data["sfp"], sfp_data["sfp_destinations"], sff_configure)
		if reg_result != 0:
			return (-10, reg_result)

		return (0,)


	def processingServer(self):

		client_control = {}
		while True:
			self.data_semaphore.acquire()
			self.data_mutex.acquire()
			recv_data = self.data_queue.pop(0)
			self.data_mutex.release()

			#print("RECV MESSAGE N#" + str(recv_data[2]), "(" + str(len(recv_data[0])) + ")", "(" + str(recv_data[1]) + ")")

			if recv_data[2] == -1:
				if recv_data[3] in client_control:
					del client_control[recv_data[3]]
				continue
			
			if not recv_data[4] in self.sfp_destinations:
				continue

			if not recv_data[3] in client_control:
				if self.neighbor_sc_majority > 1:
					client_control[recv_data[3]] = {'control':-1}
				else:
					new_nsh = self.nsh_processor.newHeader(0, 63, 1, 1, self.sfp_destinations[recv_data[4]], 0, bytearray(16))
					for sff in self.sfp_routing[self.sfp_destinations[recv_data[4]]]:
						self.ft_manager.sendMessage(self.sff_addresses[sff], (len(recv_data[0]) + len(new_nsh)).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + recv_data[0][:-len(recv_data[0]) + 14] + new_nsh + recv_data[0][14:])
					continue

			if client_control[recv_data[3]]['control'] >= recv_data[2]:
				continue

			if not recv_data[1] in self.neighbor_sc_addresses:
				for neighbor_ip in self.neighbor_sc_addresses:
					self.ft_manager.sendMessage(neighbor_ip, len(recv_data[0]).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + recv_data[0]) 

			if not recv_data[2] in client_control[recv_data[3]]:
				client_control[recv_data[3]][recv_data[2]] = [[recv_data[0], 1]]
				continue

			found_flag = False
			for index in range(len(client_control[recv_data[3]][recv_data[2]])):
				if client_control[recv_data[3]][recv_data[2]][index][0] == recv_data[0]:
					client_control[recv_data[3]][recv_data[2]][index][1] += 1
					found_flag = True
					break

			if not found_flag:
				client_control[recv_data[3]][recv_data[2]].append([recv_data[0], 1])
				continue

			if client_control[recv_data[3]][recv_data[2]][index][1] == self.neighbor_sc_majority:
				new_nsh = self.nsh_processor.newHeader(0, 63, 1, 1, self.sfp_destinations[recv_data[4]], 0, bytearray(16))
				#print("SENT MESSAGE N#" + str(recv_data[2]), "(" + str(len(recv_data[0])+len(new_nsh)) + ")")
				for sff in self.sfp_routing[self.sfp_destinations[recv_data[4]]]:
					self.ft_manager.sendMessage(self.sff_addresses[sff], (len(recv_data[0]) + len(new_nsh)).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + recv_data[0][:-len(recv_data[0]) + 14] + new_nsh + recv_data[0][14:])
				client_control[recv_data[3]]["control"] = recv_data[2]
				del client_control[recv_data[3]][recv_data[2]]


	def startServers(self):

		self.processing_server = multiprocessing.Process(target=self.processingServer)
		self.processing_server.start()
		
		self.ft_manager.requestConnections(self.neighbor_sc_addresses)
		self.ft_manager.requestConnections(list(set(self.sff_addresses.values())))


###############################################################################################################

################################################# SERVER AREA #################################################

if len(sys.argv) >= 3:
	default_net_inc_address = sys.argv[1]
	default_sc_acc_address = sys.argv[2]
	neighbor_sc_addresses = []
	for index in range(3, len(sys.argv)):
		neighbor_sc_addresses.append(sys.argv[index])
else:
	print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: SC.py EXT_IP_ADDRESS INT_IP_ADDRESS NGH_SC_IP_1 .. NGH_SC_IP_N]")
	exit()

default_http_acc_port = 8080
service_classifier = SC(default_net_inc_address, default_sc_acc_address, neighbor_sc_addresses)

@bottle.route('/status', method='GET')
def statusSC():
	return "SUCCESS: RUNNING"

@bottle.route('/setup', method='POST')
def setupSFP():

	global service_classifier

	try:
		sfp_yaml = bottle.request.forms.get("sfp_yaml")
	except:
		return bottle.HTTPResponse(status=400, body="ERROR: SFP YAML NOT PROVIDED!")

	try:
		sff_configure = eval(bottle.request.forms.get("sff_configure"))
	except:
		sff_configure = False

	resp_code = service_classifier.setupSFP(sfp_yaml, sff_configure)
	if resp_code[0] == -1:
		return bottle.HTTPResponse(status=400, body="ERROR: INAVLID YAML STRUCTURE!")
	elif resp_code[0] == -2:
		return bottle.HTTPResponse(status=400, body="ERROR: NO SFP ID IN YAML!")
	elif resp_code[0] == -3:
		return bottle.HTTPResponse(status=400, body="ERROR: NO SFP SF IN YAML!")
	elif resp_code[0] == -4:
		return bottle.HTTPResponse(status=400, body="ERROR: NO SFP SFF IN YAML!")
	elif resp_code[0] == -5:
		return bottle.HTTPResponse(status=400, body="ERROR: NO SFP SF_SFF IN YAML!")
	elif resp_code[0] == -6:
		return bottle.HTTPResponse(status=400, body="ERROR: NO SFP SFP IN YAML!")
	elif resp_code[0] == -7:
		return bottle.HTTPResponse(status=400, body="ERROR: NO SFP DESTINATIONS IN YAML!")
	elif resp_code[0] == -8:
		return bottle.HTTPResponse(status=400, body="ERROR: INVALID SFF CONFIGURE DATA PROVIDED!")
	elif resp_code[0] == -9:
		return bottle.HTTPResponse(status=400, body="ERROR: ERROR ON REGISTERING SFF (" + str(resp_code[1]) +  ")!")
	elif resp_code[0] == -10:
		return bottle.HTTPResponse(status=400, body="ERROR: ERROR ON REGISTERING SFP (" + str(resp_code[1]) +  ")!")

	return "SUCCESS: SFP SUCCESSFULLY REGISTERED!"


@bottle.route('/delete', method='POST')
def deleteSFP():

	global service_classifier

	try:
		sfp_id = bottle.request.forms.get("sfp_id")
	except:
		return bottle.HTTPResponse(status=400, body="ERROR: SFP ID NOT PROVIDED!")

	try:
		sff_configure = eval(bottle.request.forms.get("sff_configure"))
	except:
		sff_configure = False

	resp_code = service_classifier.deleteSFP(sfp_id, sff_configure)
	if resp_code == -1:
		return bottle.HTTPResponse(status=400, body="ERROR: INAVLID SFP ID PROVIDED!")
	elif resp_code == -2:
		return bottle.HTTPResponse(status=400, body="ERROR: PROCESS TERMINATED BUT SOME SFF DID NOT RECOGNIZE THE SFP ID!")

	return "SUCCESS: SFP SUCCESSFULLY DELETED"


@bottle.route('/start', method='POST')
def startSC():
	
	global service_classifier

	service_classifier.startServers()

	return "SUCCESS: SFP SUCCESSFULLY REGISTERED!"


@bottle.route('/stop', method='POST')
def stopSC():

	global service_classifier
	global http_server_lock

	service_classifier.shutdownSC()
	http_server_lock.release()

	return "SUCCESS: SC SUCCESSFULLY OFF"


@bottle.route('/lightsout', method='POST')
def stopEnvironment():

	global service_classifier
	global http_server_lock

	for sff in service_classifier.sff_addresses:
		try:
			requests.post("http://" + service_classifier.sff_addresses[sff] + ":8080/stop")
		except:
			continue

	service_classifier.shutdownSC()
	http_server_lock.release()

	return "SUCCESS: SC SUCCESSFULLY OFF"


def startHTTP():

	global default_sc_acc_address
	global default_http_acc_port
	global http_server_lock

	http_server_lock.acquire()
	http_server_process = multiprocessing.Process(target=bottle.run, kwargs=dict(host=default_sc_acc_address, port=default_http_acc_port, debug=True))
	http_server_process.start()

	return http_server_process


http_server_lock = multiprocessing.Lock()
http_server_process = startHTTP()
http_server_lock.acquire()
http_server_process.terminate()

###############################################################################################################