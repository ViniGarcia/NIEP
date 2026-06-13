//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_NAME: Policy Forward
//VNF_DESCRIPTION: Forward packets between two ports, but block IP traffic between h1 and h3

// Port 0 faces h1.
// Port 1 faces the switch where h2 and h3 are attached.

in0 :: FromDPDKDevice(0);
out0 :: ToDPDKDevice(0);

in1 :: FromDPDKDevice(1);
out1 :: ToDPDKDevice(1);

from_h1_side :: Classifier(
    12/0806, // ARP
    12/0800, // IPv4
    -
);

from_switch_side :: Classifier(
    12/0806, // ARP
    12/0800, // IPv4
    -
);

block_h1_to_h3 :: IPFilter(
    deny src 10.30.0.1 && dst 10.30.0.3,
    allow all
);

block_h3_to_h1 :: IPFilter(
    deny src 10.30.0.3 && dst 10.30.0.1,
    allow all
);

// h1 side to switch side: allow ARP, filter IPv4.
in0 -> from_h1_side;
from_h1_side[0] -> out1;
from_h1_side[1] -> CheckIPHeader(14) -> block_h1_to_h3 -> out1;
from_h1_side[2] -> Discard;

// switch side to h1 side: allow ARP, filter IPv4.
in1 -> from_switch_side;
from_switch_side[0] -> out0;
from_switch_side[1] -> CheckIPHeader(14) -> block_h3_to_h1 -> out0;
from_switch_side[2] -> Discard;
