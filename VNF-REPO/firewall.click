//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_ID:b69c308a-9bde-459a-b171-fed5621ce46d
//VNF_PROVIDER:UFSM/UFPR
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

//Addresses Definition
AddressInfo(SERVER01 192.168.121.10);
AddressInfo(SERVER02 192.168.121.11);
AddressInfo(SERVER03 192.168.121.12);
AddressInfo(CLIENT01 192.168.121.13);

//L2 Classifier
cw :: Classifier(
    12/0806, 			//ARP to cw[0] 
    12/0800, 			//IP to cw[1]
    -        			//Everything else is discarded
);

//IP Classifier
f1 :: IPClassifier(
    icmp,       		//ICMP Packets to f[0]
	tcp,       			//TCP Packets to f[1]
	udp,				//UDP Packets to f[2]
	-   				//Everything else is discarded
);

//IP Filter
f2 :: IPFilter(
	allow src CLIENT01 && dst SERVER01,		//ICMP from Client to Server01 is explicity allowed
	deny src CLIENT01 && dst SERVER02,		//ICMP from Client to Server02 is explicity denied
	deny all 								//ICMP from anywhere to any server is denied by default
);

//Forwarding Rules
in0 -> cw; 														//in0 goes to classifier (cw)
cw[0] -> CheckARPHeader(14) -> out1;    						//ARP packets pass-through
cw[1] -> CheckIPHeader(14) -> f1;        						//IP packets to IP classifier
cw[2] -> Print("UNRECOGNIZED PROTOCOL CW DROP:") -> Discard; 	//If packet is neither ARP nor IP it is discarded

f1[0] -> f2;   													//ICMP packets pass to IP filter (f2)
f1[1] -> Print("TCP PACKET FORWARDED:") -> out1;                //TCP packets pass to output 1
f1[2] -> Print("UDP PROTOCOL DROP:") -> Discard;				//UDP packets are discarded
f1[3] -> Print("UNRECOGNIZED PROTOCOL DROP:") -> Discard;		//Unrecognized packets are discarded

f2 -> Print("ICMP PACKET FORWARDED:") -> out1;					//ICMP is sent according to firewall rules

in1 -> out0; 													//in1 (from server) pass-through to out0
