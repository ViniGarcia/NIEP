import multiprocessing
import scapy.all
import struct
import socket
import sys
import re

######################################################## DNS BUILDER ########################################################

class DnsPacketBuilder:

	__type_codes = None
	__codes_type = None
	__class_codes = None
	__odes_class = None

	def __init__(self):
		
		self.__type_codes = {"A":1, "NS":2, "MD":3, "MF":4, "CNAME":5, "SOA":6, "MB":7, "MG":8, "MR":9, "NULL":10, "WKS":11, "PTR":12, "HINFO":13, "MINFO":14, "MX":15, "TXT":16}
		self.__codes_type = {1:"A", 2:"NS", 3:"MD", 4:"MF", 5:"CNAME", 6:"SOA", 7:"MB", 8:"MG", 9:"MR", 10:"NULL", 11:"WKS", 12:"PTR", 13:"HINFO", 14:"MINFO", 15:"MX", 16:"TXT"}

		self.__class_codes = {"IN":1, "CS":2, "CH":3, "HS":4}
		self.__codes_class = {1:"IN", 2:"CS", 3:"CH", 4:"HS"}

	def build_std_query(self, transaction_id, transaction_urls):
		packet = struct.pack(">H", transaction_id)
		packet += struct.pack(">H", 256)
		packet += struct.pack(">H", len(transaction_urls))
		packet += struct.pack(">H", 0)
		packet += struct.pack(">H", 0)
		packet += struct.pack(">H", 0)
		
		for url in transaction_urls:
			split_url = url.split(".")
			for part in split_url:
				packet += struct.pack("B", len(part))
				for byte in part:
					packet += struct.pack("c", bytes(byte, "utf-8"))
			packet += struct.pack("B", 0)
			packet += struct.pack(">H", 1)
			packet += struct.pack(">H", 1)

		return packet

	def read_std_query(self, recv_query):
		
		unpacked_data = {}
		unpacked_data["transaction_id"] = struct.unpack(">H", recv_query[:2])[0]
		unpacked_data["flags"] = struct.unpack(">H", recv_query[2:4])[0]
		unpacked_data["questions"] = struct.unpack(">H", recv_query[4:6])[0]
		unpacked_data["answers"] = struct.unpack(">H", recv_query[6:8])[0]
		unpacked_data["authorities"] = struct.unpack(">H", recv_query[8:10])[0]
		unpacked_data["additional"] = struct.unpack(">H", recv_query[10:12])[0]
		
		unpacked_data["queries"] = []
		unpacking_index = 12
		for query_index in range(unpacked_data["questions"]):
			query_data = ""
			
			while True:
				partial_query_len = recv_query[unpacking_index]
				unpacking_index += 1;

				if partial_query_len == 0:
					query_type = struct.unpack(">H", recv_query[unpacking_index:unpacking_index+2])
					query_class = struct.unpack(">H", recv_query[unpacking_index+2:unpacking_index+4])
					unpacking_index += 4
					unpacked_data["queries"].append((query_data[:-1], query_type, query_class, unpacking_index))
					break
				
				query_data += recv_query[unpacking_index:unpacking_index+partial_query_len].decode("utf-8") + "."
				unpacking_index += partial_query_len

		unpacked_data["responses"] = []

		return unpacked_data

	def read_std_response(self, recv_response):

		unpacked_data = {}
		unpacked_data["transaction_id"] = struct.unpack(">H", recv_response[:2])[0]
		unpacked_data["flags"] = struct.unpack(">H", recv_response[2:4])[0]
		unpacked_data["questions"] = struct.unpack(">H", recv_response[4:6])[0]
		unpacked_data["answers"] = struct.unpack(">H", recv_response[6:8])[0]
		unpacked_data["authorities"] = struct.unpack(">H", recv_response[8:10])[0]
		unpacked_data["additional"] = struct.unpack(">H", recv_response[10:12])[0]
		
		unpacked_data["queries"] = []
		unpacking_index = 12
		for query_index in range(unpacked_data["questions"]):
			query_data = ""
			
			while True:
				partial_query_len = recv_response[unpacking_index]
				unpacking_index += 1;

				if partial_query_len == 0:
					query_type = struct.unpack(">H", recv_response[unpacking_index:unpacking_index+2])[0]
					query_class = struct.unpack(">H", recv_response[unpacking_index+2:unpacking_index+4])[0]
					unpacking_index += 4
					unpacked_data["queries"].append((query_data[:-1], query_type, query_class, unpacking_index))
					break
				
				query_data += recv_response[unpacking_index:unpacking_index+partial_query_len].decode("utf-8") + "."
				unpacking_index += partial_query_len

		unpacked_data["responses"] = []
		for response_index in range(unpacked_data["answers"]):
			unpacking_index += 1
			response_offset = recv_response[unpacking_index]

			response_query = ""
			while True:
				partial_query_len = recv_response[response_offset]
				response_offset += 1;
				if partial_query_len == 0 or partial_query_len == 192:
					break
				response_query += recv_response[response_offset:response_offset+partial_query_len].decode("utf-8") + "."
				response_offset += partial_query_len
			response_query = response_query[:-1]

			unpacking_index += 1
			response_type = struct.unpack(">H", recv_response[unpacking_index:unpacking_index+2])[0]
			unpacking_index += 2
			response_class = struct.unpack(">H", recv_response[unpacking_index:unpacking_index+2])[0]
			unpacking_index += 2
			response_ttl = struct.unpack(">I", recv_response[unpacking_index:unpacking_index+4])[0]
			unpacking_index += 4
			response_local_length = struct.unpack(">H", recv_response[unpacking_index:unpacking_index+2])[0]
			unpacking_index += 2
			response_data = recv_response[unpacking_index:unpacking_index+response_local_length]

			unpacked_data["responses"].append((response_query, response_type, response_ttl, response_data, unpacking_index-11))
			unpacking_index += response_local_length

		return unpacked_data

	def create_std_response(self, recv_query, r_type, r_class, r_ttl, r_data, proc_query = None):

		if proc_query == None:
			proc_query = self.read_std_response(recv_query)

		if proc_query["answers"] == 0:
			r_name = 12
		else:
			r_name = proc_query["responses"][-1][-1] + 9

		local_response = bytes((192).to_bytes(length=1, byteorder="big"))
		local_response += ((r_name).to_bytes(length=1, byteorder="big"))
		local_response += struct.pack(">H", r_type)
		local_response += struct.pack(">H", r_class)
		local_response += struct.pack(">I", r_ttl)
		local_response += struct.pack(">H", len(r_data))
		local_response += bytes(r_data)

		return recv_query[:6] + struct.pack(">H", proc_query["answers"] + 1) + recv_query[8:] + local_response

	def create_std_response_data(self, r_type, r_data):
		
		final_result = None

		if r_type == 1:
			#r_data format: (ip_address,)
			partial_result = r_data[0].split(".")
			final_result = bytearray()
			if len(partial_result) != 4:
				return None
			for number in partial_result:
				try:
					int_number = int(number)
				except:
					return None
				if int_number < 0 or int_number > 255:
					return None
				final_result.extend(bytes((int_number,)))
		elif r_type == 5:
			#r_data format: (dns_name,)
			partial_result = r_data[0].split(".")
			final_result = bytearray()
			for pr in partial_result:
				final_result.extend(bytes((len(pr),)))
				final_result.extend(bytes(pr, "utf-8"))
		
		return final_result

#############################################################################################################################


################################################### DNS CLIENT FUNCTIONS ####################################################


def setup(target_name, server_ip, server_port, client_ip, client_port):

	global std_target_name
	global std_server_ip
	global std_server_port
	global std_client_ip
	global std_client_port

	if not re.match("[0-9]+(?:\\.[0-9]+){3}", server_ip):
		return -1
	if not re.match("[0-9]+(?:\\.[0-9]+){3}", client_ip):
		return -2
	if not server_port.isnumeric():
		return -3
	if not client_port.isnumeric():
		return -4

	std_target_name = target_name
	std_server_ip = server_ip
	std_server_port = int(server_port)
	std_client_ip = client_ip
	std_client_port = int(client_port)
	return 0

def query(dns_builder):

	global std_target_name
	global std_server_ip
	global std_server_port
	global std_client_ip
	global std_client_port

	global message_identifier
	global destination_conns

	query_packet = dns_builder.build_std_query(12049, [std_target_name])
	udp_packet = bytes(scapy.all.Ether(src='00:00:00:00:02:01', dst='00:00:00:00:00:00')/scapy.all.IP(src=std_client_ip, dst=std_server_ip)/scapy.all.UDP(sport=std_client_port, dport=std_server_port)/query_packet)
	ft_packet = len(udp_packet).to_bytes(2, byteorder='big') + message_identifier.to_bytes(4, byteorder='big') + udp_packet
	message_identifier += 1

	eliminate = []
	for conn in destination_conns:
		try:
			conn.sendall(ft_packet)
		except:
			eliminate.append(conn)

	if len(eliminate) > 0:
		for conn in eliminate:
			conn.close()
			destination_conns.remove(conn)


def server(recv_socket, dns_builder, fault_tolerance):
	
	responses_dictionary = {}
	responses_counter = -1

	while True:

		try:
			dns_response, dns_address = resp_socket.recvfrom(1024)
		except:
			break

		response_id = struct.unpack(">I", dns_response[-4:])[0]
		dns_response = dns_response[:-4]

		if response_id <= responses_counter:
			if response_id in responses_dictionary:
				del responses_dictionary[response_id]
			continue

		if fault_tolerance == 0:
			print("\n", dns_builder.read_std_response(dns_response), "\n")
			continue

		if not response_id in responses_dictionary:
			responses_dictionary[response_id] = {dns_response:[dns_address[0]]}
			continue
		else:
			if dns_response in responses_dictionary[response_id]:
				if not dns_address[0] in responses_dictionary[response_id][dns_response]:
					responses_dictionary[response_id][dns_response].append(dns_address[0])
				if len(responses_dictionary[response_id][dns_response]) == fault_tolerance + 1:
					print("\n", dns_builder.read_std_response(dns_response), "\n")
					del responses_dictionary[response_id]
					responses_counter = response_id

#############################################################################################################################


################################################### SIMPLE EDGE DNS CLIENT ##################################################

#DNS REQUEST VARIABLES: employed to create a request
std_target_name = None
std_server_ip = None
std_server_port = None
std_client_ip = None
std_client_port = None

#VARIABLE: number employed to mark messages (used for FT strategies)
message_identifier = 0
#VARIABLE: TCP connections with the target service classifiers
destination_conns = []


'''
PROGRAM STANDARD ARGUMENTS: this program expects a sequence of IP addresses to which it will open TCP connections. So,
							the client must be initialized when the IP entities are already responding in the standard
							port 12000.
'''
if len(sys.argv) > 1:
	try:
		fault_tolerance = int(sys.argv[1])
	except:
		print("ERROR: INVALID FAULT TOLERANCE ARGUMENT PROVIDED! [EXPECTED: DNS-Client.py FAULT_TOLERANCE SC_IP_1 SC_IP_2 .. SC_IP_N]")
		exit()
else:
	print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: DNS-Client.py FAULT_TOLERANCE SC_IP_1 SC_IP_2 .. SC_IP_N]")
	exit()

if len(sys.argv) > 2:
	for index in range(2, len(sys.argv)):
		if re.match("[0-9]+(?:\\.[0-9]+){3}", sys.argv[index]):
			new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			new_socket.connect((sys.argv[index], 12000))
			destination_conns.append(new_socket)
		else:
			print("WARNING: INVALID IP (" + sys.argv[index] + ")")
else:
	print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: DNS-Client.py FAULT_TOLERANCE SC_IP_1 SC_IP_2 .. SC_IP_N]")
	exit()

std_dns_builder = DnsPacketBuilder()


#STANDARD SETUP FOR TESTS
setup("www.facebook.com", "192.168.123.3", "53", "192.168.122.1", "9999") #JUST FOR TESTS

# SOCKET FOR RECEIVING THE RESPONSE FROM THE DNS SERVER
resp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
resp_socket.bind(('192.168.122.1', 9999))

server_process = multiprocessing.Process(target=server, kwargs=dict(recv_socket=resp_socket, dns_builder=std_dns_builder, fault_tolerance=fault_tolerance))
server_process.start()

'''
PROGRAM MAIN LOOP: this program provides a very simple interface for the user. Through this interface, the user can
				   request the action "send" to trigger a packet sending for the destination connections.
'''
while True:
	action = input("Enter Action: ")
	if action.startswith("setup"):
		setup_args = action.split(" ")
		if len(setup_args) != 6:
			print("ERROR: INVALID SETUP ARGUMENTS PROVIDED!")
			continue
		setup_res = setup(setup_args[1], setup_args[2], setup_args[3], setup_args[4], setup_args[5])
		if setup_res < 0:
			print("ERROR: INVALID SETUP ATTEMPT (" + str(setup_res) + ")!")
			continue

	if action.startswith("send"):
		if std_target_name == None:
			print("ERROR: NO SETUP PREVIOUSLY EXECUTED!")
			continue
		query(std_dns_builder)

	if action.startswith("stop"):
		resp_socket.close()
		server_process.terminate()
		for conn in destination_conns:
			conn.close()
		exit()

#############################################################################################################################