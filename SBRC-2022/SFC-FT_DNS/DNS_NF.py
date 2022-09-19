import multiprocessing
import struct
import socket
import math
import sys
import re

import NSH
import NM

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

#Function that returns True if a given string represents and IPv4 without netmask, and return False otherwise
def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())

#Main segment that receives the NF ip as argument and validates it
if len(sys.argv) == 2:
    nf_acc_address = sys.argv[1]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: NF.py IP_ADDRESS]")
    exit()
if not isIP(nf_acc_address):
    print("ERROR: INVALID IP PROVIDED!")
    exit()

#Main segment that create all the require resources to the NF operation in our context of FT
nsh_processor = NSH.NSH()

#Main segment that work as a server, receiving, checking duplicates (FT), processing, and forwarding packets
pkt_manager = multiprocessing.Manager()
pkt_list = pkt_manager.list()
pkt_mutex = pkt_manager.Lock()
pkt_semaphore = pkt_manager.Semaphore(0)

ft_manager = NM.NET_MANAGER(nf_acc_address, pkt_list, pkt_mutex, pkt_semaphore, True)
ft_manager.startServer()

#DNS Resources
dns_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
dns_socket.bind((nf_acc_address, 53))
dns_socket.settimeout(3)
dns_builder = DnsPacketBuilder()
dns_dictionary = {"www.facebook.com":"31.13.88.35",#
                  "www.google.com":"142.251.45.110"}

print("\nNF RUNNING FOR PROCESSING PACKETS\n")
client_control = {}
while True:

    pkt_semaphore.acquire()
    pkt_mutex.acquire()
    recv_data = pkt_list.pop(0)
    pkt_mutex.release()

    if recv_data[2] == -1:
        if recv_data[3] in client_control:
            del client_control[recv_data[3]]
            continue

    try:
        nsh_processor.fromHeader(recv_data[0][14:][:-len(recv_data[0]) + 38])
    except:
        continue

    if not recv_data[3] in client_control:
        client_control[recv_data[3]] = {'control':-1}

    if client_control[recv_data[3]]['control'] >= recv_data[2]:
        continue

    if not recv_data[2] in client_control[recv_data[3]]:
        if len(ft_manager.getConnections()) > 3:
            client_control[recv_data[3]][recv_data[2]] = [1, [recv_data[0], 1]]
        else:
            nsh_processor.service_si += 1
            try:
                recv_request = dns_builder.read_std_query(recv_data[0][66:])
            except:
                continue
            if len(recv_request["queries"]) > 0:
                if recv_request["queries"][0][0] in dns_dictionary:
                    snd_response = dns_builder.create_std_response(recv_data[0][66:], 1, 1, 65000, dns_builder.create_std_response_data(1, (dns_dictionary[recv_request["queries"][0][0]],)), recv_request) + struct.pack(">I", recv_data[2])
                    snd_address = (recv_data[3], struct.unpack(">H", recv_data[0][58:60])[0])
                    dns_socket.sendto(snd_response, snd_address)
                else:
                    dns_socket.sendto(recv_data[0][66:], ("8.8.8.8", 53))
                    snd_response = dns_socket.recvfrom(1024) + struct.pack(">I", recv_data[2])
                    snd_address = (recv_data[3], struct.unpack(">H", recv_data[0][58:60])[0])
                    dns_socket.sendto(snd_response, snd_address)
            client_control[recv_data[3]]['control'] = recv_data[2]
        continue

    found_flag = False
    for index in range(1, len(client_control[recv_data[3]][recv_data[2]])):
        if client_control[recv_data[3]][recv_data[2]][index][0] == recv_data[0]:
            client_control[recv_data[3]][recv_data[2]][index][1] += 1
            found_flag = True
            break

    if not found_flag:
        client_control[recv_data[3]][recv_data[2]].append([recv_data[0], 1])
        index += 1

    client_control[recv_data[3]][recv_data[2]][0] += 1

    faults_parameter = math.floor((len(ft_manager.getConnections()) - 1) / 3)
    waiting_parameter = 2 * faults_parameter + 1
    majority_parameter = faults_parameter + 1

    if client_control[recv_data[3]][recv_data[2]][0] >= waiting_parameter:

        for index in range(1, len(client_control[recv_data[3]][recv_data[2]])):

            if client_control[recv_data[3]][recv_data[2]][index][1] >= majority_parameter:
                nsh_processor.service_si += 1
                try:
                    recv_request = dns_builder.read_std_query(recv_data[0][66:])
                except:
                    continue
                if len(recv_request["queries"]) > 0:
                    if recv_request["queries"][0][0] in dns_dictionary:
                        snd_response = dns_builder.create_std_response(recv_data[0][66:], 1, 1, 65000, dns_builder.create_std_response_data(1, (dns_dictionary[recv_request["queries"][0][0]],)), recv_request) + struct.pack(">I", recv_data[2])
                        snd_address = (recv_data[3], struct.unpack(">H", recv_data[0][58:60])[0])
                        dns_socket.sendto(snd_response, snd_address)
                    else:
                        dns_socket.sendto(recv_data[0][66:], ("8.8.8.8", 53))
                        snd_response = dns_socket.recvfrom(1024) + struct.pack(">I", recv_data[2])
                        snd_address = (recv_data[3], struct.unpack(">H", recv_data[0][58:60])[0])
                        dns_socket.sendto(snd_response, snd_address)
                client_control[recv_data[3]]['control'] = recv_data[2]
                del client_control[recv_data[3]][recv_data[2]]
                break