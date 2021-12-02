import multiprocessing
import netifaces
import bottle
import socket
import sys
import re

import NSH

################################################## SFF AREA ###################################################

class SFF:

	__default_port = 12000
	int_interface_access = None
	ext_interface_access = None

	data_manager = None
	entity_addresses = None
	traffic_routes = None

	nsh_processor = None

	sff_server = None

	packet_control = None
	ft_checking = None


	def __init__(self, int_interface_access_ip, ext_interface_access_id, ft_checking):
		
		self.int_interface_access = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
		if int_interface_access_ip != None:
			self.int_interface_access.bind((int_interface_access_ip, self.__default_port))
		else:
			self.int_interface_access.bind((self.getIP(), self.__default_port))

		self.ext_interface_access = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
		self.ext_interface_access.bind((ext_interface_access_id, 0))

		self.ft_checking = ft_checking

		self.data_manager = multiprocessing.Manager()
		self.entity_addresses = self.data_manager.dict()
		self.traffic_routes = self.data_manager.dict()

		self.nsh_processor = NSH.NSH()

		self.packet_control = self.data_manager.dict()

	def __del__(self):

		if self.sff_server != None:
			self.sff_server.terminate()

		self.int_interface_access.close()


	def __isIP(self, potential_ip):

		return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())


	def __isMAC(self, potential_mac):

		return re.match("[0-9a-f]{2}([-:]?)[0-9a-f]{2}(\\1[0-9a-f]{2}){4}$", potential_mac.lower())


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
			#self.traffic_routes = {**self.traffic_routes}
		if service_path in self.entity_addresses:
			self.entity_addresses.pop(service_path)
			#self.entity_addresses = {**self.entity_addresses}
		return 0

	def sffServer(self):

		while True:
			incoming_data = self.int_interface_access.recv(65535)

			try:
				self.nsh_processor.fromHeader(incoming_data[14:][:-len(incoming_data) + 38])
			except:
				continue

			origin_id = int.from_bytes(incoming_data[58:62], "big")
			message_id = int.from_bytes(incoming_data[-4:], "big")
			if origin_id in self.packet_control:
				if self.packet_control[origin_id][0] > message_id:
					continue
				if self.packet_control[origin_id][0] == message_id and self.packet_control[origin_id][1] == self.nsh_processor.service_si:
					if not self.packet_control[origin_id][2]:
						continue
					for index in range(3, len(self.packet_control[origin_id])):
						if incoming_data == self.packet_control[origin_id][index][0]:
							self.packet_control[origin_id] = self.packet_control[origin_id][:index] + [[self.packet_control[origin_id][index][0], self.packet_control[origin_id][index][1] + 1]] + self.packet_control[origin_id][index+1:]
							break
					if index == len(self.packet_control[origin_id]):
						self.packet_control[origin_id] = self.packet_control[origin_id] + [[incoming_data, 1]]
				else:
					self.packet_control[origin_id] = [message_id, self.nsh_processor.service_si, True, [incoming_data, 1]]
					index = -1
			else:
				self.packet_control[origin_id] = [message_id, self.nsh_processor.service_si, True, [incoming_data, 1]]
				index = -1
			
			if self.packet_control[origin_id][index][1] == self.ft_checking:
				self.packet_control[origin_id] =  self.packet_control[origin_id][:2] + [False] + self.packet_control[origin_id][3:]

				target_entity = self.traffic_routes[self.nsh_processor.service_spi][self.nsh_processor.service_si]
				for target_address in self.entity_addresses[self.nsh_processor.service_spi][target_entity]:
					if target_address != None:
						self.int_interface_access.sendto(incoming_data, (target_address, self.__default_port))
					else:
						self.ext_interface_access.send(incoming_data[:-len(incoming_data) + 14] + incoming_data[38:])

	def startServers(self):

		self.sff_server = multiprocessing.Process(target=self.sffServer)
		self.sff_server.start()

###############################################################################################################

################################################# SERVER AREA #################################################

if len(sys.argv) == 3:
	sf_forwarder = SFF(None, sys.argv[1], int(sys.argv[2]))
	ft_checking = int(sys.argv[2])
	default_sff_int_acc_ip = sf_forwarder.getIP()
elif len(sys.argv) == 4:
	if not re.match("[0-9]+(?:\\.[0-9]+){3}", sys.argv[1]):
		print("ERROR: INVALID IP ADDRESS PROVIDED!")
		exit()
	sf_forwarder = SFF(sys.argv[1], sys.argv[2], int(sys.argv[3]))
	default_sff_int_acc_ip = sys.argv[1]
else:
	print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: SFF.py [INT_IP_ADDRESS] EXT_IFACE_ID FT_CHECKING]")
	exit()

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

	del sf_forwarder
	http_server_lock.release()


def startHTTP():

	global default_sff_int_acc_ip
	global default_http_acc_port
	global http_server_lock

	http_server_lock.acquire()
	http_server_process = multiprocessing.Process(target=bottle.run, kwargs=dict(host=default_sff_int_acc_ip, port=default_http_acc_port, debug=True))
	http_server_process.start()

	return http_server_process

sf_forwarder.startServers()
http_server_lock = multiprocessing.Lock()
http_server_process = startHTTP()
http_server_lock.acquire()
http_server_process.terminate()

###############################################################################################################