import multiprocessing
import math
import sys
import re

import NSH
import NMC

server_ips = [b'\xc0\xa8|\x01', b'\xc0\xa8|\x02']
server_macs = [b'\x00\x00\x00\x00\x02\x18', b'\x00\x00\x00\x00\x02\x19'] #BE AWARE OF THE MAC PROBLEM
round_robin = 0

def selectDestination(recv_pckt):
    global server_ips
    global server_macs
    global round_robin

    new_pckt = server_macs[round_robin] + recv_pckt[6:54] + server_ips[round_robin] + recv_pckt[58:]
    round_robin = (round_robin + 1) % len(server_ips)
    
    return new_pckt

#Function that returns True if a given string represents and IPv4 without netmask, and return False otherwise
def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())

#Main segment that receives the NF ip as argument and validates it
if len(sys.argv) == 3:
    nf_acc_address = sys.argv[1]
    consensus_file_path = sys.argv[2]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: NF.py IP_ADDRESS CONSENSUS_FILE_PATH]")
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

ft_manager = NMC.NET_MANAGER(nf_acc_address, pkt_list, pkt_mutex, pkt_semaphore, True, consensus_file_path)
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
            new_frame = selectDestination(recv_data[0])
            nsh_processor.service_si += 1
            ft_manager.broadcastMessage(len(new_frame).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + new_frame[:-len(new_frame)+14] + nsh_processor.toHeader() + new_frame[38:])
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

    if client_control[recv_data[3]][recv_data[2]][0] >= waiting_parameter:

        for index in range(1, len(client_control[recv_data[3]][recv_data[2]])):
            if client_control[recv_data[3]][recv_data[2]][index][1] >= waiting_parameter:
                new_frame = selectDestination(client_control[recv_data[3]][recv_data[2]][index][0])
                nsh_processor.service_si += 1
                ft_manager.broadcastMessage(len(new_frame).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + new_frame[:-len(new_frame)+14] + nsh_processor.toHeader() + new_frame[38:])
                client_control[recv_data[3]]['control'] = recv_data[2]
                del client_control[recv_data[3]][recv_data[2]]
                break
