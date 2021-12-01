import socket
import sys
import re

msg_id = 0

def send(sc_ips):
    global msg_id

    samplePacket = b'\xf4\xe5\xf2\xd5{\xa1(\xe3G\x0b\x0e\xb2\x08\x00E\x00\x00<\xc3l@\x00@\x11\xd1\xe7\xc0\xa8\x12\x0b\xc0\xa8|\x01\xb7\x86\x005\x00(;\xeb\xd7\xf2\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03www\x06google\x03com\x00\x00\x01\x00\x01' + msg_id.to_bytes(4, byteorder='big')
    msg_id += 1

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
    for ip in sc_ips:
        udp_socket.sendto(samplePacket, (ip, 12000))
        print("SENT DATA [" + ip + "]: ", samplePacket, "\n")
    udp_socket.close()


sc_ips = []
if len(sys.argv) > 0:
    for index in range(1, len(sys.argv)):
        if re.match("[0-9]+(?:\\.[0-9]+){3}", sys.argv[index]):
            sc_ips.append(sys.argv[index])
        else:
            print("WARNING: INVALID IP (" + sys.argv[index] + ")")
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Client.py SC_IP_1 SC_IP_2 .. SC_IP_N]")
    exit()


while True:
    action = input("Enter action: ")
    if action == "send":
        send(sc_ips)
