import multiprocessing
import netifaces
import bottle
import socket
import math
import sys
import re

import NSH
import NM

################################################## SFF AREA ###################################################

class SFF:

	__int_interface_ip = None
	__ext_interface_id = None

	data_manager = None
	data_queue = None
	data_mutex = None
	data_semaphore = None

	data_ext_socket = None

	entity_addresses = None
	traffic_routes = None

	nsh_processor = None

	ft_manager = None

	processing_server = None


	def __init__(self, int_interface_ip, ext_interface_id):
		
		self.__int_interface_ip = int_interface_ip
		self.__ext_interface_id = ext_interface_id

		self.data_manager = multiprocessing.Manager()
		self.data_queue = self.data_manager.list()
		self.data_mutex = self.data_manager.Lock()
		self.data_semaphore = self.data_manager.Semaphore(0)

		self.data_ext_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
		self.data_ext_socket.bind((ext_interface_id, 0))

		self.entity_addresses = self.data_manager.dict()
		self.traffic_routes = self.data_manager.dict()

		self.nsh_processor = NSH.NSH()

		if self.__int_interface_ip == None:
			self.__int_interface_ip = self.getIP()
		self.ft_manager = NM.NET_MANAGER(self.__int_interface_ip, self.data_queue, self.data_mutex, self.data_semaphore, True)
		self.ft_manager.startServer()


	def __isIP(self, potential_ip):

		return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())


	def __isMAC(self, potential_mac):

		return re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", potential_mac.lower())


	def shutdownSFF(self):

		if self.ft_manager != None:
			self.ft_manager.shutdownManager()

		if self.processing_server != None:
			self.processing_server.terminate()

		if self.data_ext_socket != None:
			self.data_ext_socket.close()


	def getIP(self):
		phy_interfaces = netifaces.interfaces()
		if "lo" in phy_interfaces:
			phy_interfaces.append(phy_interfaces.pop(phy_interfaces.index("lo")))

		for pi in phy_interfaces:
			phy_addresses = netifaces.ifaddresses(pi)
			if not netifaces.AF_INET in phy_addresses:
				continue
			return phy_addresses[netifaces.AF_INET][0]['addr']

		return "127.0.0.1"


	def registerEntity(self, service_path, service_index, ip_address):

		try:
			service_path = int(service_path)
		except:
			return -1
		try:
			service_index = int(service_index)
		except:
			return -2
		try:
			if ip_address != None:
				ip_address = str(ip_address)
				if not self.__isIP(ip_address):
					return -4
		except:
			return -3

		if not service_path in self.entity_addresses:
			self.entity_addresses[service_path] = {}
		if not service_index in self.entity_addresses[service_path]:
			self.entity_addresses[service_path] = {**self.entity_addresses[service_path], **{service_index:[ip_address]}}
		else:
			self.entity_addresses[service_path] = {**self.entity_addresses[service_path], **{service_index:[ip_address] + self.entity_addresses[service_path][service_index]}}

		if service_index > 0 and ip_address != None:
			self.ft_manager.requestConnections([ip_address])

		return 0


	def registerRoute(self, service_path, service_index, next_destination):

		try:
			service_path = int(service_path)
		except:
			return -1
		try:
			service_index = int(service_index)
		except:
			return -2
		try:
			next_destination = int(next_destination)
		except:
			if next_destination != None:
				return -3
			else:
				pass

		if not service_path in self.entity_addresses:
			return -4
		if not service_index in self.entity_addresses[service_path]:
			return -5
		if not next_destination in self.entity_addresses[service_path] and next_destination != None:
			return -6

		if not service_path in self.traffic_routes:
			self.traffic_routes[service_path] = {}
		self.traffic_routes[service_path] = {**self.traffic_routes[service_path], **{service_index:next_destination}}
		return 0


	def deleteSFP(self, service_path):

		try:
			service_path = int(service_path)
		except:
			return -1

		if service_path in self.traffic_routes:
			self.traffic_routes.pop(service_path)
		if service_path in self.entity_addresses:
			self.entity_addresses.pop(service_path)
		return 0


	def sffServer(self):

		client_control = {}
		while True:
			self.data_semaphore.acquire()
			self.data_mutex.acquire()
			recv_data = self.data_queue.pop(0)
			self.data_mutex.release()

			#print("RECV MESSAGE N#" + str(recv_data[2]), "(" + str(len(recv_data[0])) + ")")

			if recv_data[2] == -1:
				if recv_data[3] in client_control:
					del client_control[recv_data[3]]
				continue

			try:
				self.nsh_processor.fromHeader(recv_data[0][14:][:-len(recv_data[0]) + 38])
			except:
				continue

			if not recv_data[3] in client_control:
				client_control[recv_data[3]] = {'control':-1}

			if client_control[recv_data[3]]['control'] >= recv_data[2]:
				continue

			if not recv_data[2] in client_control[recv_data[3]]:
				client_control[recv_data[3]][recv_data[2]] = {'control':-1}

			if client_control[recv_data[3]][recv_data[2]]['control'] > self.nsh_processor.service_si:
				continue

			if not self.nsh_processor.service_si in client_control[recv_data[3]][recv_data[2]]:
				client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si] = [[recv_data[0], 1]]
				index = 0
			else:
				found_flag = False
				for index in range(len(client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si])):
					if recv_data[0] == client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si][index][0]:
						client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si][index][1] += 1
						found_flag = True
						break

				if not found_flag:
					client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si].append([recv_data[0], 1])
					index += 1

			ft_parameter = math.ceil(len(self.entity_addresses[self.nsh_processor.service_spi][self.nsh_processor.service_si]) / 2 + 0.1)


			#print("PARAM MESSAGE N#" + str(recv_data[2]), "(" + str(index) + ")", "(" + str(client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si][index][1]) + ")", "(" + str(len(client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si])) + "," + str(self.nsh_processor.service_si) + ")")
			if client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si][index][1] == ft_parameter:

				target_entity = self.traffic_routes[self.nsh_processor.service_spi][self.nsh_processor.service_si]
				if self.entity_addresses[self.nsh_processor.service_spi][target_entity][0] == None:
					#print("SENT MESSAGE FINAL N#" + str(recv_data[2]), "(" + str(len(recv_data[0])) + ")")
					self.data_ext_socket.send(recv_data[0][:-len(recv_data[0]) + 14] + recv_data[0][38:] + recv_data[2].to_bytes(4, byteorder='big'))
					del client_control[recv_data[3]][recv_data[2]]
					client_control[recv_data[3]]['control'] = recv_data[2]
				else:
					#print("SENT MESSAGE MID N#" + str(recv_data[2]), "(" + str(len(recv_data[0])) + ")")
					for target_address in self.entity_addresses[self.nsh_processor.service_spi][target_entity]:
						self.ft_manager.sendMessage(target_address, len(recv_data[0]).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + recv_data[0])
					del client_control[recv_data[3]][recv_data[2]][self.nsh_processor.service_si]
					client_control[recv_data[3]][recv_data[2]]['control'] = self.nsh_processor.service_si


	def startServers(self):

		self.processing_server = multiprocessing.Process(target=self.sffServer)
		self.processing_server.start()

###############################################################################################################

################################################# SERVER AREA #################################################

if len(sys.argv) < 3:
	print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: SFF.py INT_IP_ADDRESS EXT_IFACE_ID]")
	exit()
else:
	int_interface_ip = sys.argv[1]
	ext_interface_id = sys.argv[2]
	sf_forwarder = SFF(int_interface_ip, ext_interface_id)
	
default_http_acc_port = 8080


@bottle.route('/entity', method='POST')
def registerEntity():

	global sf_forwarder

	try:
		service_path = bottle.request.forms.get("service_path")
		service_index = bottle.request.forms.get("service_index")
		ip_address = bottle.request.forms.get("ip_address")
	except:
		return bottle.HTTPResponse(status=400, body="ERROR: INCOMPLETE FORM PROVIDED!")	

	resp_code = sf_forwarder.registerEntity(service_path, service_index, ip_address)
	if resp_code == -1:
		return bottle.HTTPResponse(status=400, body="ERROR: INAVLID SERVICE PATH PROVIDED!")
	elif resp_code == -2:
		return bottle.HTTPResponse(status=400, body="ERROR: INVALID SERVICE INDEX PROVIDED!")
	elif resp_code == -3:
		return bottle.HTTPResponse(status=400, body="ERROR: INVALID IP ADDRESS PROVIDED!")
	elif resp_code == -4:
		return bottle.HTTPResponse(status=400, body="ERROR: INVALID IP ADDRESS FORMAT!")
	
	return "SUCCESS: ENTITY SUCCESSFULLY REGISTERED!"


@bottle.route('/route', method='POST')
def registerRoute():

	global sf_forwarder

	try:
		service_path = bottle.request.forms.get("service_path")
		service_index = bottle.request.forms.get("service_index")
		next_destination = bottle.request.forms.get("next_destination")
	except:
		return bottle.HTTPResponse(status=400, body="ERROR: INCOMPLETE FORM PROVIDED!")	

	resp_code = sf_forwarder.registerRoute(service_path, service_index, next_destination)
	if resp_code == -1:
		return bottle.HTTPResponse(status=400, body="ERROR: INAVLID SERVICE PATH PROVIDED!")
	elif resp_code == -2:
		return bottle.HTTPResponse(status=400, body="ERROR: INVALID SERVICE INDEX PROVIDED!")
	elif resp_code == -3:
		return bottle.HTTPResponse(status=400, body="ERROR: INVALID NEXT DESTINATION PROVIDED!")
	elif resp_code == -4:
		return bottle.HTTPResponse(status=400, body="ERROR: SERVICE PATH IS NOT REGISTERED!")
	elif resp_code == -5:
		return bottle.HTTPResponse(status=400, body="ERROR: SERVICE INDEX IS NOT REGISTERED!")
	elif resp_code == -6:
		return bottle.HTTPResponse(status=400, body="ERROR: NEXT DESTINATION IS NOT REGISTERED!")

	return "SUCCESS: ROUTE SUCCESSFULLY REGISTERED!"


@bottle.route('/delete', method='POST')
def deleteSFP():

	global sf_forwarder

	try:
		service_path = bottle.request.forms.get("service_path")
	except:
		return bottle.HTTPResponse(status=400, body="ERROR: INCOMPLETE FORM PROVIDED!")

	resp_code = sf_forwarder.deleteSFP(service_path)
	if resp_code == -1:
		return bottle.HTTPResponse(status=400, body="ERROR: INAVLID SERVICE PATH PROVIDED!")

	return "SUCCESS: SFP SUCCESSFULLY DELETED!"


@bottle.route('/stop', method='POST')
def stopSFF():

	global sf_forwarder
	global http_server_lock

	sf_forwarder.shutdownSFF()
	http_server_lock.release()


def startHTTP():

	global int_interface_ip
	global default_http_acc_port
	global http_server_lock

	http_server_lock.acquire()
	http_server_process = multiprocessing.Process(target=bottle.run, kwargs=dict(host=int_interface_ip, port=default_http_acc_port, debug=True))
	http_server_process.start()

	return http_server_process

sf_forwarder.startServers()
http_server_lock = multiprocessing.Lock()
http_server_process = startHTTP()
http_server_lock.acquire()
http_server_process.terminate()

###############################################################################################################
