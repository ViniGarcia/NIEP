import socket
import sys

if len(sys.argv) == 2:
    ser_acc_iface = sys.argv[1]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Server.py SER_ACC_INTERFACE]")
    exit()

interface_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
interface_socket.bind((ser_acc_iface, 0))

packet_control = {}

while True:
    pkt_data = interface_socket.recv(10240)

    origin_id = int.from_bytes(pkt_data[34:38], "big")
    message_id = int.from_bytes(pkt_data[-4:], "big")
    if origin_id in packet_control:
        if packet_control[origin_id] >= message_id:
            continue
    packet_control[origin_id] = message_id
    
    print("DELIVERED DATA: ", pkt_data, len(pkt_data), "\n")

interface_socket.close()