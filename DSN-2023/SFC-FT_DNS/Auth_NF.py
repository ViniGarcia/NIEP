import multiprocessing
import math
import sys
import re

import os.path

from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from Crypto.Signature import pkcs1_15

import NSH
import NM

#Function that returns True if a given string represents and IPv4 without netmask, and return False otherwise
def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())

#Main segment that receives the NF ip as argument and validates it
if len(sys.argv) == 3:
    nf_acc_address = sys.argv[1]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: NF.py IP_ADDRESS PVT_KEY_FILE]")
    exit()
if not isIP(nf_acc_address):
    print("ERROR: INVALID IP PROVIDED!")
    exit()

if os.path.isfile(sys.argv[2]):
    try:
        key_file = open(sys.argv[2])
        client_std_pubkey = RSA.importKey(key_file.read())
        key_file.close()
    except Exception as e:
        print("ERROR: INVALID KEY FILE PROVIDED!")
        exit()
else:
    print("ERROR: INVALID KEY FILE PATH PROVIDED! [EXPECTED: NF.py IP_ADDRESS PVT_KEY_FILE]")
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
            signature = recv_data[0][66:][-256:]
            message = recv_data[0][66:][:-256]
            try:
                pkcs1_15.new(client_std_pubkey).verify(SHA256.new(message), signature)
            except (ValueError, TypeError):
                continue
            unsigned_message = recv_data[0][:-256]
            nsh_processor.service_si += 1
            ft_manager.broadcastMessage(len(unsigned_message).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + unsigned_message[:-len(unsigned_message)+14] + nsh_processor.toHeader() + unsigned_message[38:])
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


                signature = client_control[recv_data[3]][recv_data[2]][0][66:][-256:]
                message = client_control[recv_data[3]][recv_data[2]][0][66:][:-256]
                try:
                    pkcs1_15.new(client_std_pubkey).verify(SHA256.new(message), signature)
                except (ValueError, TypeError):
                    break

                client_control[recv_data[3]][recv_data[2]][0] = client_control[recv_data[3]][recv_data[2]][0][:-256]
                nsh_processor.service_si += 1
                ft_manager.broadcastMessage(len(client_control[recv_data[3]][recv_data[2]][index][0]).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + client_control[recv_data[3]][recv_data[2]][index][0][:-len(client_control[recv_data[3]][recv_data[2]][index][0])+14] + nsh_processor.toHeader() + client_control[recv_data[3]][recv_data[2]][index][0][38:])
                client_control[recv_data[3]]['control'] = recv_data[2]
                del client_control[recv_data[3]][recv_data[2]]
                break