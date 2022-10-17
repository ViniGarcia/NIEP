import multiprocessing
import socket
import struct

############################################## NET MANAGER AREA ##############################################

class NET_MANAGER:

	__default_port = 12000
	__default_net_ip = None
	__default_net_socket = None

	__connection_server = None
	__connection_manager = None
	__connection_sockets = None
	__connection_processes = None

	__data_queue = None
	__data_mutex = None
	__data_semaphore = None

	__consensus_id = None
	__consensus_port = 12001
	__consensus_socket = None
	__consensus_elements = None

	__consensus_base = None
	__consensus_check = None
	__consensus_mutex = None
	__consensus_semaphore = None

	__nsh_flag = None

	def __init__(self, default_net_ip, data_queue, data_mutex, data_semaphore, nsh_flag, consensus_elements_file = "/home/research/Desktop/NIEP/SBRC-2022/SFC-FT_Consensus/ConsensusConf.csv"):

		self.__default_net_ip = default_net_ip
		self.__default_net_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.__default_net_socket.bind((self.__default_net_ip, self.__default_port))
		self.__default_net_socket.listen(1024)

		self.__connection_manager = multiprocessing.Manager()
		self.__connection_sockets = self.__connection_manager.dict()
		self.__connection_processes = {}
		
		self.__data_queue = data_queue
		self.__data_mutex = data_mutex
		self.__data_semaphore = data_semaphore

		try:
			consensus_file = open(consensus_elements_file, "r")
		except:
			print("ERROR [NMC]: INVALID CONSENSUS FILE PATH PROVIDED!")
			exit()

		self.__consensus_elements = self.__connection_manager.dict()
		for line in consensus_file:
			try:
				line = line.split(";")
				line[1] = line[1].strip().replace("\n", "")
				if line[1] == self.__default_net_ip:
					self.__consensus_id = int(line[0])
				else:
					self.__consensus_elements[line[1]] = (int(line[0]), )
			except:
				print("ERROR [NMC]: INVALID CONSENSUS FILE DATA!")
				exit()

		if self.__consensus_id == None:
			print("ERROR [NMC]: ELEMENT NOT INCLUDED IN THE CONSENSUS FILE!")
			exit()
		self.__consensus_processes = {}

		self.__consensus_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		self.__consensus_socket.bind((self.__default_net_ip, self.__consensus_port))
		self.__consensus_socket.listen(1024)

		self.__consensus_base = self.__connection_manager.dict()
		self.__consensus_check = self.__connection_manager.dict()
		self.__consensus_mutex = self.__connection_manager.Lock()

		self.__nsh_flag = nsh_flag


	def shutdownManager(self):

		self.__data_mutex.acquire()

		for process_id in self.__connection_processes:
			self.__connection_processes[process_id].terminate()

		sockets_list = self.__connection_sockets.keys()
		for socket_id in sockets_list:
			self.__connection_sockets[socket_id].shutdown(socket.SHUT_RDWR)
			self.__connection_sockets[socket_id].close()

		if self.__connection_server != None:
			self.__connection_server.terminate()

		self.__default_net_socket.shutdown(socket.SHUT_RDWR)
		self.__default_net_socket.close()

		self.__data_mutex.release()


	def conRecvServer(self, consensus_connection, consensus_ip):

		while True:
			consensus_msg = consensus_connection.recv(10)
			
			data_mark = int.from_bytes(consensus_msg[:2], "big")
			data_origin = str(int(consensus_msg[2])) + "." + str(int(consensus_msg[3])) + "." + str(int(consensus_msg[4])) + "." + str(int(consensus_msg[5]))
			data_detination = str(int(consensus_msg[6])) + "." + str(int(consensus_msg[7])) + "." + str(int(consensus_msg[8])) + "." + str(int(consensus_msg[9]))
			data_key = (data_mark, data_origin, data_detination)

			#PRE-PREPARE
			self.__consensus_mutex.acquire()
			if not data_key in self.__consensus_check:
				if self.__consensus_elements[consensus_ip][0] == 0:
					self.__consensus_check[data_key] = (2, [0, self.__consensus_id])
					for element in self.__consensus_elements.keys():
						self.__consensus_elements[element][1].send(consensus_msg)
				else:
					continue
			#WEAK ACCEPT
			else:
				if not self.__consensus_elements[consensus_ip][0] in self.__consensus_check[data_key][1]:
					self.__consensus_check[data_key] = (self.__consensus_check[data_key][0]+1, self.__consensus_check[data_key][1] + [self.__consensus_elements[consensus_ip][0]])
			self.__consensus_mutex.release()

			self.__consensus_mutex.acquire()
			if data_key in self.__consensus_check:
				if self.__consensus_check[data_key][0] == len(self.__consensus_elements) + 1:
					if data_key in self.__consensus_base:
						self.__data_mutex.acquire()
						self.__data_queue.append(self.__consensus_base[data_key])
						self.__consensus_base.pop(data_key)
						self.__consensus_check.pop(data_key)
						self.__data_semaphore.release()
						self.__data_mutex.release()
			self.__consensus_mutex.release()

	def conConnectionServer(self):

		while True:
			consensus_connection, consensus_address = self.__consensus_socket.accept()
			if not consensus_address[0] in self.__consensus_elements:
				consensus_connection.close()
				continue
			consensus_process = multiprocessing.Process(target = self.conRecvServer, kwargs = dict(consensus_connection=consensus_connection, consensus_ip=consensus_address[0]))
			consensus_process.start()
			self.__consensus_elements[consensus_address[0]] = (self.__consensus_elements[consensus_address[0]][0], consensus_connection)
			self.__consensus_processes[consensus_address[0]] = consensus_process


	def conRequestConnection(self):

		for ip in self.__consensus_elements.keys():
			if self.__consensus_elements[ip][0] < self.__consensus_id:
				consensus_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				try:
					consensus_socket.connect((ip, self.__consensus_port))
				except:
					print("WARNING: UNABLE TO CONNECT WITH " + ip + " TO ESTABLISH THE CONSENSUS CHAIN!")
					consensus_socket.close()
					continue
				consensus_process = multiprocessing.Process(target = self.conRecvServer, kwargs = dict(consensus_connection=consensus_socket, consensus_ip=ip))
				consensus_process.start()
				self.__consensus_elements[ip] = (self.__consensus_elements[ip][0], consensus_socket)
				self.__consensus_processes[ip] = consensus_process


	def conPropose(self, data_mark, data_origin_ip, data_destination_ip):
		
		proposal_message = struct.pack(">H", data_mark)
		for address_fragment in data_origin_ip.split("."):
			proposal_message += int(address_fragment).to_bytes(1, "big")
		for address_fragment in data_destination_ip.split("."):
			proposal_message += int(address_fragment).to_bytes(1, "big")

		self.__consensus_mutex.acquire()
		self.__consensus_check[(data_mark, data_origin_ip, data_destination_ip)] = (1, [self.__consensus_id])
		self.__consensus_mutex.release()
		for element in self.__consensus_elements.keys():
			self.__consensus_elements[element][1].send(proposal_message)


	def msgRecvServer(self, client_connection, client_ip):
		
		while True:
			client_metadata = client_connection.recv(6)
			
			if len(client_metadata) == 6:
				data_length = int.from_bytes(client_metadata[:2], "big")
				data_mark = int.from_bytes(client_metadata[2:], "big")

				client_data = b''
				while len(client_data) != data_length:
					client_data += client_connection.recv(data_length - len(client_data))
				
				if len(client_data) == data_length:
					if not self.__nsh_flag:
						data_origin_ip = client_data[26:][:-len(client_data) + 30]
						data_origin_ip = str(data_origin_ip[0]) + "." + str(data_origin_ip[1]) + "." + str(data_origin_ip[2]) + "." + str(data_origin_ip[3])
						data_destination_ip = client_data[30:][:-len(client_data) + 34]
						data_destination_ip = str(data_destination_ip[0]) + "." + str(data_destination_ip[1]) + "." + str(data_destination_ip[2]) + "." + str(data_destination_ip[3])
					else:
						data_origin_ip = client_data[50:][:-len(client_data) + 54]
						data_origin_ip = str(data_origin_ip[0]) + "." + str(data_origin_ip[1]) + "." + str(data_origin_ip[2]) + "." + str(data_origin_ip[3])
						data_destination_ip = client_data[54:][:-len(client_data) + 58]
						data_destination_ip = str(data_destination_ip[0]) + "." + str(data_destination_ip[1]) + "." + str(data_destination_ip[2]) + "." + str(data_destination_ip[3])

					self.__consensus_base[(data_mark, data_origin_ip, data_destination_ip)] = (client_data, client_ip, data_mark, data_origin_ip, data_destination_ip)
					if self.__consensus_id == 0:
						self.conPropose(data_mark, data_origin_ip, data_destination_ip)
					
			if len(client_metadata) == 0:
				self.__data_mutex.acquire()
				self.__data_queue.append(('', client_ip, -1, client_ip, ''))
				self.__data_semaphore.release()
				self.__data_mutex.release()
				return


	def msgConnectionServer(self):

		while True:
			client_connection, client_address = self.__default_net_socket.accept()
			client_process = multiprocessing.Process(target = self.msgRecvServer, kwargs = dict(client_connection=client_connection, client_ip=client_address[0]))
			client_process.start()
			self.__connection_sockets[client_address[0]] = client_connection
			self.__connection_processes[client_address[0]] = client_process


	def requestConnections(self, servers_ip):

		for ip in servers_ip:
			if not ip in self.__connection_sockets:	
				server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				try:
					server_socket.connect((ip, self.__default_port))
				except:
					server_socket.close()
					continue
				server_process = multiprocessing.Process(target = self.msgRecvServer, kwargs = dict(client_connection=consensus_socket, client_ip=ip))
				server_process.start()
				self.__connection_sockets[ip] = server_socket
				self.__connection_processes[ip] = server_process


	def sendMessage(self, server_ip, message_data):

		if not server_ip in self.__connection_sockets:
			return -1

		try:
			self.__connection_sockets[server_ip].send(message_data)
		except:
			if server_ip in self.__connection_processes:
				self.__connection_processes[server_ip].terminate()
				del self.__connection_processes[server_ip]
			self.__connection_sockets[server_ip].close()
			del self.__connection_sockets[server_ip]


	def broadcastMessage(self, message_data):

		sockets_list = self.__connection_sockets.keys()
		
		eliminate_server = []
		for server_ip in sockets_list:
			try:
				self.__connection_sockets[server_ip].send(message_data)
			except:
				eliminate_server.append(server_ip)

		if len(eliminate_server) > 0:
			for server_ip in eliminate_server:
				if server_ip in self.__connection_processes:
					self.__connection_processes[server_ip].terminate()
					del self.__connection_processes[server_ip]
				self.__connection_sockets[server_ip].close()
				del self.__connection_sockets[server_ip]


	def getConnections(self):

		return list(self.__connection_sockets.keys())


	def startServer(self):

		self.client_connection_server = multiprocessing.Process(target=self.msgConnectionServer)
		self.client_connection_server.start()
		self.consensus_connection_server = multiprocessing.Process(target=self.conConnectionServer)
		self.consensus_connection_server.start()
		self.conRequestConnection()

###############################################################################################################