import multiprocessing
import socket

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

	__nsh_flag = None


	def __init__(self, default_net_ip, data_queue, data_mutex, data_semaphore, nsh_flag):

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


	def recvServer(self, client_connection, client_ip):
		
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
						data_origin_ip = client_data[34:][:-len(client_data) + 38]
						data_origin_ip = str(data_origin_ip[0]) + "." + str(data_origin_ip[1]) + "." + str(data_origin_ip[2]) + "." + str(data_origin_ip[3])
						data_destination_ip = client_data[30:][:-len(client_data) + 34]
						data_destination_ip = str(data_destination_ip[0]) + "." + str(data_destination_ip[1]) + "." + str(data_destination_ip[2]) + "." + str(data_destination_ip[3])
					else:
						data_origin_ip = client_data[58:][:-len(client_data) + 62]
						data_origin_ip = str(data_origin_ip[0]) + "." + str(data_origin_ip[1]) + "." + str(data_origin_ip[2]) + "." + str(data_origin_ip[3])
						data_destination_ip = client_data[54:][:-len(client_data) + 58]
						data_destination_ip = str(data_destination_ip[0]) + "." + str(data_destination_ip[1]) + "." + str(data_destination_ip[2]) + "." + str(data_destination_ip[3])

					self.__data_mutex.acquire()
					self.__data_queue.append((client_data, client_ip, data_mark, data_origin_ip, data_destination_ip))
					self.__data_semaphore.release()
					self.__data_mutex.release()

			if len(client_metadata) == 0:
				self.__data_mutex.acquire()
				self.__data_queue.append(('', client_ip, -1, client_ip, ''))
				self.__data_semaphore.release()
				self.__data_mutex.release()
				return


	def connectionServer(self):

		while True:
			client_connection, client_address = self.__default_net_socket.accept()
			client_process = multiprocessing.Process(target = self.recvServer, kwargs = dict(client_connection=client_connection, client_ip=client_address[0]))
			client_process.start()
			self.__connection_sockets[client_address[0]] = client_connection
			self.__connection_processes[client_address[0]] = client_process


	def requestConnections(self, servers_ip):

		for ip in servers_ip:
			if not ip in self.__connection_sockets:	
				server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
				try:
					server_socket.connect((ip, 12000))
				except:
					server_socket.close()
					continue
				server_process = multiprocessing.Process(target = self.recvServer, kwargs = dict(client_connection=server_socket, client_ip=ip))
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


	def startServer(self):

		self.client_connection_server = multiprocessing.Process(target=self.connectionServer)
		self.client_connection_server.start()

###############################################################################################################