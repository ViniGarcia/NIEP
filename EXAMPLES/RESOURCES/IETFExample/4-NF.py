import socket
import sys
import re

import NSH

#Function that returns True if a given string represents and IPv4 without netmask, and return False otherwise
def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())

#Main segment that receives the NF ip as argument and validates it
if len(sys.argv) > 3:
    nf_acc_address = sys.argv[1]
    
    try:
        ft_checking = int(sys.argv[2])
    except:
        print("ERROR: INVALID ft_checking PROVIDED!")
        exit()

    sff_addresses = []
    for index in range(3, len(sys.argv)):
        if isIP(sys.argv[index]):
            sff_addresses.append(sys.argv[index])
        else:
            print("WARNING: INVALID IP (" + sys.argv[index] + ")")
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: NF.py IP_ADDRESS FT_CHECKING SC_IP_1 .. SC_IP_N]")
    exit()

if not isIP(nf_acc_address):
    print("ERROR: INVALID IP PROVIDED!")
    exit()

#Main segment that create all the require resources to the NF operation in our context of FT
std_port = 12000
packet_control = {}
nsh_processor = NSH.NSH()
interface_access = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
interface_access.bind((nf_acc_address, 12000))

#Main segment that work as a server, receiving, checking duplicates (FT), processing, and forwarding packets
print("\nSUCCESS - NF SERVER STARTED\n")
while True:
    pkt_data, sff_addr = interface_access.recvfrom(10240)

    if not sff_addr[0] in sff_addresses:
        continue
    
    # FILTER COMPONENT - BEGIN #
    origin_id = int.from_bytes(pkt_data[58:62], "big")
    message_id = int.from_bytes(pkt_data[-4:], "big")
    if origin_id in packet_control:
        if packet_control[origin_id][0] > message_id:
            continue
        if packet_control[origin_id][0] == message_id:
            if not packet_control[origin_id][1]:
                continue
            for index in range(2, len(packet_control[origin_id])):
                if pkt_data == packet_control[origin_id][index][0]:
                    packet_control[origin_id][index][1] = packet_control[origin_id][index][1] + 1
                    break
            if index == len(packet_control[origin_id]):
                packet_control[origin_id].append([[pkt_data, 1]])
        else:
            packet_control[origin_id] = [message_id, True, [pkt_data, 1]]
            index = -1
    else:
        packet_control[origin_id] = [message_id, True, [pkt_data, 1]]
        index = -1
    # FILTER COMPONENT - END #

    if packet_control[origin_id][index][1] == ft_checking:
        packet_control[origin_id][1] = False


        print("PROCESSED DATA: ", pkt_data, len(pkt_data), "\n")

        nsh_processor.fromHeader(pkt_data[14:][:-len(pkt_data)+38])
        nsh_processor.service_si += 1
        pkt_data = pkt_data[:-len(pkt_data)+14] + nsh_processor.toHeader() + pkt_data[38:]

        for address in sff_addresses:
            interface_access.sendto(pkt_data, (address, std_port))

interface_access.close()