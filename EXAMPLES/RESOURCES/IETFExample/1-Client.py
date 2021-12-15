import socket
import sys
import re

#VARIABLE: number employed to mark messages (used for FT strategies)
message_identifier = 0
#VARIABLE: TCP connections with the target service classifiers
destination_conns = []

'''
FUNCTION: this function sends a dummy packet to the connections in "destination_conns". It inserts the message length (2 bytes)
          and the message identifier ("message_identifier" - 4 bytes) as the first data segment in the payload. The total packet
          length is defined by the argument called "packet_length". The minimum packet length, in turn, is 43 bytes.
'''
def send_packet(packet_length):
    global message_identifier
    global destination_conns

    dummy_packet = b'\xf4\xe5\xf2\xd5{\xa1(\xe3G\x0b\x0e\xb2\x08\x00E\x00\x00<\xc3l@\x00@\x11\xd1\xe7\xc0\xa8\x12\x0b\xc0\xa8|\x01\xb7\x86\x005\x00(;\xeb'
    dummy_payload = 0 

    if packet_length > 42:
        payload_size = packet_length - 42
    else:
        print("WARNING: PACKET LENGTH IS TOO SMALL; CHANGED TO 43 BYTES!")
        payload_size = 1

    for index in range(payload_size):
        dummy_packet += dummy_payload.to_bytes(1, byteorder='big')
    

    dummy_packet = len(dummy_packet).to_bytes(2, byteorder='big') + message_identifier.to_bytes(4, byteorder='big') + dummy_packet
    message_identifier += 1

    for conn in destination_conns:
        conn.sendall(dummy_packet)

'''
PROGRAM STANDARD ARGUMENTS: this program expects a sequence of IP addresses to which it will open TCP connections. So,
                            the client must be initialized when the IP entities are already responding in the standard
                            port 12000.
'''
if len(sys.argv) > 1:
    for index in range(1, len(sys.argv)):
        if re.match("[0-9]+(?:\\.[0-9]+){3}", sys.argv[index]):
            new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_socket.connect((sys.argv[index], 12000))
            destination_conns.append(new_socket)
        else:
            print("WARNING: INVALID IP (" + sys.argv[index] + ")")
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Client.py SC_IP_1 SC_IP_2 .. SC_IP_N]")
    exit()

'''
PROGRAM MAIN LOOP: this program provides a very simple interface for the user. Through this interface, the user can
                   request the action "send" to trigger a packet sending for the destination connections.
'''
while True:
    action = input("Enter Action: ")
    if action.startswith("send"):
        args = action.split(" ")
        if len(args) == 2:
            try:
                packet_length = int(args[1])
            except:
                print("ERROR: INVALID ARGUMENT PROVIDED (REQUIRE AN INTEGER NUMBER)\n")
                continue    
        else:
            print("ERROR: THIS ACTION REQUIRE ONE ARGUMENT (send packet_length)\n")
            continue

        send_packet(packet_length)