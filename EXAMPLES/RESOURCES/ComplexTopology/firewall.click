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

AddressInfo(HOST01 192.168.122.1);
AddressInfo(HOST02 192.168.122.2);
AddressInfo(HOST03 192.168.123.1);
AddressInfo(HOST04 192.168.123.2);
AddressInfo(SERVER01 192.168.124.1);
AddressInfo(SERVER02 192.168.124.2);
AddressInfo(SERVER03 192.168.124.3);

cw :: Classifier(
    12/0806, 			//ARP
    12/0800, 			//IP
    -        			
);

f1 :: IPClassifier(
    icmp,
	tcp,
	udp,
	-
);

f2 :: IPFilter(
	deny src HOST03 && dst SERVER03,
	allow all
);

in0 -> cw;
cw[0] -> CheckARPHeader(14) -> out1;
cw[1] -> CheckIPHeader(14) -> f1;
cw[2] -> Discard;

f1[0] -> f2;
f1[1] -> f2;                
f1[2] -> f2;
f1[3] -> Discard;

f2 -> out1;

in1 -> out0;
