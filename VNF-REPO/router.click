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

// Port 0, 00:00:00:00:02:01, 192.168.121.1
// Port 1, 00:00:00:00:02:02, 192.168.122.1

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

net0in -> Print("1: ") -> [0]c0;
net1in -> [0]c1;

//ARP
arpq1 :: ARPQuerier(192.168.121.1, 00:00:00:00:02:01);
arpq0 :: ARPQuerier(192.168.122.1, 00:00:00:00:02:02);

t :: Tee(2);
c0[1] -> Print("2: ") -> t;
c1[1] -> t;
t[0] -> Print("3.1: ") -> [1]arpq0;
t[1] -> Print("3.2: ") -> [1]arpq1;

arpq0 -> Print("5: ") -> net0out;
arpq1 -> net1out;

arpr0 :: ARPResponder(192.168.122.1 00:00:00:00:02:02);
arpr1 :: ARPResponder(192.168.121.1 00:00:00:00:02:01);
c0[0] -> Print("4: ") -> arpr0 -> Print("4.1: ") -> net0out;
c1[0] -> arpr1 -> net1out;

rt :: StaticIPLookup(
	192.168.121.0/24 0,
	192.168.122.0/24 1);

ip :: Strip(14) -> CheckIPHeader(INTERFACES 192.168.121.1/24 192.168.122.1/24) -> [0]rt;
c0[2] -> Print("6: ") -> ip;
c1[2] -> ip;

rt[0] -> Print("7: ") -> DropBroadcasts -> FixIPSrc(192.168.121.1) -> [0]arpq0;
rt[1] -> DropBroadcasts -> FixIPSrc(192.168.122.1) -> [0]arpq1;
