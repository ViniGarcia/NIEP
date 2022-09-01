import multiprocessing
import math
import sys
import re

import NSH
import NM

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
            ft_manager.broadcastMessage(len(recv_data[0]).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + recv_data[0][:-len(recv_data[0])+14] + nsh_processor.toHeader() + recv_data[0][38:])
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

        #print(recv_data[2], client_control[recv_data[3]][recv_data[2]])

        for index in range(1, len(client_control[recv_data[3]][recv_data[2]])):

            #print(client_control[recv_data[3]][recv_data[2]][index][1], majority_parameter, faults_parameter)
            if client_control[recv_data[3]][recv_data[2]][index][1] >= majority_parameter:
                nsh_processor.service_si += 1
                ft_manager.broadcastMessage(len(client_control[recv_data[3]][recv_data[2]][index][0]).to_bytes(2, byteorder='big') + recv_data[2].to_bytes(4, byteorder='big') + client_control[recv_data[3]][recv_data[2]][index][0][:-len(client_control[recv_data[3]][recv_data[2]][index][0])+14] + nsh_processor.toHeader() + client_control[recv_data[3]][recv_data[2]][index][0][38:])
                client_control[recv_data[3]]['control'] = recv_data[2]
                del client_control[recv_data[3]][recv_data[2]]
                break