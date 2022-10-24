import socket
import time
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

    dummy_packet = b'\x00\x00\x00\x00\x02\x07\x00\x00\x00\x00\x02\x01\x08\x00E\x00\x00\x1c\x00\x01\x00\x00@\x11\x03}\xc0\xa8z\x01\xc0\xa8|\x01\x1ea\x005\x00\x08i\xf4'
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

    eliminate = []
    for conn in destination_conns:
        try:
            conn.sendall(dummy_packet)
        except:
            eliminate.append(conn)

    if len(eliminate) > 0:
        for conn in eliminate:
            conn.close()
            destination_conns.remove(conn)

'''
FUNCTION:
'''
def measure_packet(packet_length, n_packets):
    global message_identifier

    time_sheet = open("time_sheet_client.csv", "w+")

    for pkt in range(n_packets):
        print(message_identifier)
        send_time = time.time()
        send_packet(packet_length)
        time_sheet.write(str(message_identifier-1) + ";" + str(round(send_time, 3)) + "\n")
        time.sleep(0.1)

    time_sheet.close()


'''
FUNCTION:
'''
def fail_test():
    global message_identifier

    time_sheet = open("time_sheet_client.csv", "w+")

    moments = [("ALL WORKING", 1), ("FAIL NF01", 10), ("FAIL SC", 10), ("FAIL SFF", 10), ("FAIL NF02", 10), ("FAIL NF01 AND NF02", 15), ("FAIL SC AND SFF", 15)]


    for m in moments:
        print(m[0])
        time_sheet.write(m[0] + "\n")
        time.sleep(m[1])
        print("\nSTART")
        for pkt in range(100):
            send_time = time.time()
            send_packet(1024)
            time_sheet.write(str(message_identifier-1) + ";" + str(round(send_time, 3)) + "\n")
            time.sleep(0.1)
        print("\nEND")


    time_sheet.close()


'''
FUNCTION:
'''
def exit_client():
    global destination_conns

    for conn in destination_conns:
        conn.close()


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

    elif action.startswith("measure"):
        args = action.split(" ")
        if len(args) == 3:
            try:
                packet_length = int(args[1])
            except:
                print("ERROR: INVALID ARGUMENT PROVIDED (packet_length REQUIRES AN INTEGER NUMBER)\n")
                continue

            try:
                n_packets = int(args[2])
            except:
                print("ERROR: INVALID ARGUMENT PROVIDED (n_packets REQUIRES AN INTEGER NUMBER)\n")
                continue

        else:
            print("ERROR: THIS ACTION REQUIRE TWO ARGUMENTS (measure packet_length n_packets)\n")
            continue

        measure_packet(packet_length, n_packets)

    elif action.startswith("fail"):
        fail_test()

    elif action.startswith("exit"):

        exit_client()
        exit()

    else:
        print("ERROR: INAVLID OPERATION\n")