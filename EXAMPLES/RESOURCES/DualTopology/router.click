//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_ID:9196f99f-2270-48f4-a814-57206e658d24
//VNF_PROVIDER:UFSM/UFPR
//VNF_NAME: Static Router
//VNF_RELEASE_DATE:2017-04-08 21-45-45
//VNF_RELEASE_VERSION:1.0
//VNF_RELEASE_LIFESPAN:2017-06-08 21-45
//VNF_DESCRIPTION: Static Router between two /24 networks


net0in :: FromDPDKDevice(0);
net0out :: ToDPDKDevice(0);

net1in :: FromDPDKDevice(1);
net1out :: ToDPDKDevice(1);

// Port 0, 00:00:00:00:02:04, 192.168.123.2
// Port 0, 00:00:00:00:02:03, 192.168.123.1
// Port 1, 00:00:00:00:02:07, 192.168.124.1

c0 :: Classifier(12/0806 20/0001,
                  12/0806 20/0002,
                  12/0800,
                  -);

c1 :: Classifier(12/0806 20/0001,
                  12/0806 20/0002,
                  12/0800,
                  -);

c0[3] -> Discard;
c1[3] -> Discard;

net0in -> [0]c0;
net1in -> [0]c1;

//ARP
arpq2 :: ARPQuerier(192.168.123.2, 00:00:00:00:02:04);
arpq1 :: ARPQuerier(192.168.123.1, 00:00:00:00:02:03);
arpq0 :: ARPQuerier(192.168.124.1, 00:00:00:00:02:07);

t :: Tee(3);
c0[1] -> t;
c1[1] -> t;
t[0] -> [1]arpq0;
t[1] -> [1]arpq1;
t[2] -> [1]arpq2;

arpq0 -> net0out;
arpq1 -> net1out;
arpq2 -> net1out;

arpr0 :: ARPResponder(192.168.124.1 00:00:00:00:02:07);
arpr1 :: ARPResponder(192.168.123.1 00:00:00:00:02:03, 192.168.123.2 00:00:00:00:02:04);
c0[0] -> arpr0 -> net0out;
c1[0] -> arpr1 -> net1out;

rt :: StaticIPLookup(
	192.168.123.1 0,
	192.168.123.2 1,
	192.168.124.0/24 2);

ip :: Strip(14) -> CheckIPHeader(INTERFACES 192.168.123.1/24 192.168.123.2/24 192.168.124.1/24) -> [0]rt;
c0[2] -> ip;
c1[2] -> ip;

ipc :: IPClassifier(
	 src ip 192.168.123.1,
     src ip 192.168.123.2,
     -);

rt[0] -> DropBroadcasts -> FixIPSrc(192.168.123.1) -> [0]arpq0;
rt[1] -> DropBroadcasts -> FixIPSrc(192.168.123.2) -> [0]arpq0;
rt[2] -> DropBroadcasts -> FixIPSrc(192.168.124.1) -> ipc;

ipc[0] -> [0]arpq1;
ipc[1] -> [0]arpq2;
ipc[2] -> Discard();