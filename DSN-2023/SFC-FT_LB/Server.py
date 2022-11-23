import atexit
import socket
import time
import sys


#Main segment that receives the NF access interface name as argument and validates it
if len(sys.argv) == 4:
    ser_acc_iface = sys.argv[1]
    try:
        ser_register = int(sys.argv[3])
    except:
        print("ERROR: INVALID REGISTER_TIME PROVIDED! (0|1)")
        exit()
    try:
        waiting_parameter = 2 * int(sys.argv[2]) + 1
    except:
        print("ERROR: INVALID FAULTS_TOLERATED PROVIDED! (>=0)")
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Server.py SER_ACC_INTERFACE FAULTS_TOLERATED REGISTER_TIME]")
    exit()

def exit_handler():
    global interface_socket
    global time_sheet

    interface_socket.close()
    if ser_register:
        time_sheet.close()
    atexit.register(exit_handler)


#Main segment that create all the require resources to the NF operation in our context of FT
interface_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
interface_socket.bind((ser_acc_iface, 0))
packet_control = {}

if ser_register:
    time_sheet = open("time_sheet_server.csv", "w+")

#Main segment that work as a server, receiving, checking duplicates (FT), and consuming packets
while True:
    pkt_data = interface_socket.recv(10240)
    recv_time = time.time()

    if len(pkt_data) >= 100:
        origin_id = int.from_bytes(pkt_data[34:38], "big")
        message_id = int.from_bytes(pkt_data[-4:], "big")

        if origin_id in packet_control:
            if packet_control[origin_id][0] >= message_id:
                continue
            elif message_id in packet_control[origin_id][1]:
                if pkt_data in packet_control[origin_id][1][message_id][1]:
                    packet_control[origin_id][1][message_id][1][pkt_data] += 1
                else:
                    packet_control[origin_id][1][message_id][1][pkt_data] = 1
                packet_control[origin_id][1][message_id][0] += 1
            else:
                packet_control[origin_id][1][message_id] = [1, {pkt_data:1}]
        else:
            packet_control[origin_id] = [-1, {message_id:[1, {pkt_data:1}]}]

        if packet_control[origin_id][1][message_id][0] >= waiting_parameter:
            for pkt in packet_control[origin_id][1][message_id][1]:
                if packet_control[origin_id][1][message_id][1][pkt] == waiting_parameter:

                    print("DELIVERED DATA: ", pkt, len(pkt), "\n")
                    packet_control[origin_id][0] = message_id
                    packet_control[origin_id][1].pop(message_id)
                    if ser_register:
                        time_sheet.write(str(message_id) + ";" + str(round(recv_time, 3)) + "\n")