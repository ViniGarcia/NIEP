import socket
import sys
import re

#Incremental number employed to mark messages (used for FT strategies)
message_identifier = 0

#Function that sends a sample packet. It includes the message identifies as the last thing in the payload
#It opens and close an UDP socket per message sending (it can be changed according to the requires experiment)
#The function sends the message to a list of IPs called "destinations ips", in our scenario they must be the IPs of SCs
def send_packet(destination_ips):
    global message_identifier

    sample_packet = b'\xf4\xe5\xf2\xd5{\xa1(\xe3G\x0b\x0e\xb2\x08\x00E\x00\x00<\xc3l@\x00@\x11\xd1\xe7\xc0\xa8\x12\x0b\xc0\xa8|\x01\xb7\x86\x005\x00(;\xeb\xd7\xf2\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03www\x06google\x03com\x00\x00\x01\x00\x01' + message_identifier.to_bytes(4, byteorder='big')
    message_identifier += 1

    udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
    for ip in destination_ips:
        udp_socket.sendto(sample_packet, (ip, 12000))
        print("SENT DATA [" + ip + "]: ", sample_packet, "\n")
    udp_socket.close()

#Destination IPs for sending messages
destination_ips = []

#We receive the destinations IPs as arguments. We validate the IPs and add the valid ones to the destination IPs
if len(sys.argv) > 1:
    for index in range(1, len(sys.argv)):
        if re.match("[0-9]+(?:\\.[0-9]+){3}", sys.argv[index]):
            destination_ips.append(sys.argv[index])
        else:
            print("WARNING: INVALID IP (" + sys.argv[index] + ")")
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Client.py SC_IP_1 SC_IP_2 .. SC_IP_N]")
    exit()

#Server loop. There is a single operation for the client: send
while True:
    action = input("Enter Action: ")
    if action == "send":
        send_packet(destination_ips)
