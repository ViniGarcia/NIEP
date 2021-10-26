import socket
import sys
import re

import NSH


def isIP(potential_ip):
    return re.match("[0-9]+(?:\\.[0-9]+){3}", potential_ip.lower())


if len(sys.argv) == 2:
    nf_acc_address = sys.argv[1]
else:
    print("ERROR: INVALID ARGUMENTS PROVIDED! [EXPECTED: NF.py IP_ADDRESS]")
    exit()

if not isIP(nf_acc_address):
    print("ERROR: INVALID IP PROVIDED!")
    exit()

nsh_processor = NSH.NSH()
interface_access = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_IP)
interface_access.bind((nf_acc_address, 12000))
while True:
    pkt_data, sff_addr = interface_access.recvfrom(10240)
    
    print("RECV DATA: ", pkt_data, len(pkt_data), "\n")

    nsh_processor.fromHeader(pkt_data[14:][:-len(pkt_data)+38])
    nsh_processor.service_si += 1
    pkt_data = pkt_data[:-len(pkt_data)+14] + nsh_processor.toHeader() + pkt_data[38:]

    interface_access.sendto(pkt_data, sff_addr)

interface_access.close()