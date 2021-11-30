import socket
import sys

msg_id = 0

def send(cli_iface):
    global msg_id

    samplePacket = b'\xf4\xe5\xf2\xd5{\xa1(\xe3G\x0b\x0e\xb2\x08\x00E\x00\x00<\xc3l@\x00@\x11\xd1\xe7\xc0\xa8\x12\x0b\xc0\xa8|\x01\xb7\x86\x005\x00(;\xeb\xd7\xf2\x01\x00\x00\x01\x00\x00\x00\x00\x00\x00\x03www\x06google\x03com\x00\x00\x01\x00\x01' + msg_id.to_bytes(4, byteorder='big')
    msg_id += 1

    interface_socket = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(3))
    interface_socket.bind((cli_iface, 0))
    interface_socket.send(samplePacket)
    print("SENT DATA: ", samplePacket, "\n")
    interface_socket.close()


if len(sys.argv) == 2:
    cli_acc_interface = sys.argv[1]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: Client.py CLI_ACC_INTERFACE]")
    exit()


while True:
    action = input("Enter action: ")
    if action == "send":
        send(cli_acc_interface)
