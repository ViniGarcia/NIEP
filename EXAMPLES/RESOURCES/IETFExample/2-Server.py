import socket
import sys

#Main segment that receives the NF access interface name as argument and validates it
if len(sys.argv) == 2:
    ser_acc_iface = sys.argv[1]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Server.py SER_ACC_INTERFACE]")
    exit()

#Main segment that create all the require resources to the NF operation in our context of FT
interface_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
interface_socket.bind((ser_acc_iface, 0))
packet_control = {}

#Main segment that work as a server, receiving, checking duplicates (FT), and consuming packets
while True:
    pkt_data = interface_socket.recv(10240)

    # FILTER COMPONENT - BEGIN #
    origin_id = int.from_bytes(pkt_data[34:38], "big")
    message_id = int.from_bytes(pkt_data[-4:], "big")
    if origin_id in packet_control:
        if packet_control[origin_id] >= message_id:
            continue
    packet_control[origin_id] = message_id
    # FILTER COMPONENT - END #
    
    print("DELIVERED DATA: ", pkt_data, len(pkt_data), "\n")

interface_socket.close()