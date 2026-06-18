//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_NAME: UDP Packet Rate Shaper
//VNF_DESCRIPTION: Forward L2 traffic and police UDP from port 0 to port 1

// Port 0 faces the iperf3 client side.
// Port 1 faces the iperf3 server side.
// UDP above 200 packets/s from client to server is discarded.

in0 :: FromDPDKDevice(0);
out0 :: ToDPDKDevice(0);

in1 :: FromDPDKDevice(1);
out1 :: ToDPDKDevice(1);

from_client :: Classifier(
    12/0806, // ARP
    12/0800, // IPv4
    -
);

udp_or_other :: IPClassifier(
    udp,
    -
);

policer :: RatedSplitter(200);

in0 -> from_client;
from_client[0] -> out1;
from_client[1] -> CheckIPHeader(14) -> udp_or_other;
from_client[2] -> Discard;

udp_or_other[0] -> policer;
udp_or_other[1] -> out1;

policer[0] -> out1;
policer[1] -> Discard;

// Reverse traffic is pass-through so iperf3 control/response packets return.
in1 -> out0;
