//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_ID:b69c308a-9bde-459a-b171-fed5621ce46d
//VNF_PROVIDER:UFSM
//VNF_NAME:Stateless Firewall
//VNF_RELEASE_DATE:2017-04-08 21-45-45
//VNF_RELEASE_VERSION:1.0
//VNF_RELEASE_LIFESPAN:2017-06-08 21-45
//VNF_DESCRIPTION: Example stateless firewall

//Simple Stateless firewall
//Based on ClickOS stateless firewall
//Firewall rules are applied only to packets from Input 0

in0 :: FromDPDKDevice(0);
out0 :: ToDPDKDevice(0);

in1 :: FromDPDKDevice(1);
out1 :: ToDPDKDevice(1);

//L2 Classifier
cw :: Classifier(
    12/0806, //ARP to cw[0] 
    12/0800, //IP to cw[1]
    -        //Everything else is discarded
);
//IP Classifier
f :: IPClassifier(
    icmp,       //ICMP Packets to f[0]
	tcp,       //TCP Packets to f[1]
	-   //Everything else is discarded
);

in0 -> cw; //in0 goes to classifier
cw[0] -> CheckARPHeader(14) -> out1;    //ARP packets pass-through
cw[1] -> CheckIPHeader(14) -> f;        //IP packets to IP classifier
cw[2] -> Print("Drop (Not IP or ARP Packet)") -> Discard; //If packet is neither ARP nor IP it is discarded

f[0] -> Print("ICMP Drop") -> Discard();   //ICMP Packets are dropped
f[1] -> out1;                   //TCP packets pass to output 1
f[2] -> Discard();
in1 -> out0; //in1 pass-through to out0
