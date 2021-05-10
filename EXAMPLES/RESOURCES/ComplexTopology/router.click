//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_ID:9196f99f-2270-48f4-a814-57206e658d24
//VNF_PROVIDER:UFSM/UFPR
//VNF_NAME: Static Router
//VNF_RELEASE_DATE:2017-04-08 21-45-45
//VNF_RELEASE_VERSION:1.0
//VNF_RELEASE_LIFESPAN:2017-06-08 21-45
//VNF_DESCRIPTION: Static Router among three /24 networks


net0in :: FromDPDKDevice(0);
net0out :: ToDPDKDevice(0);

net1in :: FromDPDKDevice(1);
net1out :: ToDPDKDevice(1);

// Port 0, 00:00:00:00:02:01, 192.168.122.1
// Port 0, 00:00:00:00:02:02, 192.168.122.2
// Port 0, 00:00:00:00:02:03, 192.168.123.1
// Port 0, 00:00:00:00:02:04, 192.168.123.2

// Port 1, 00:00:00:00:02:05, 192.168.124.1
// Port 1, 00:00:00:00:02:06, 192.168.124.2
// Port 1, 00:00:00:00:02:07, 192.168.124.3

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
arpq_h1 :: ARPQuerier(192.168.122.1, 00:00:00:00:02:01);
arpq_h2 :: ARPQuerier(192.168.122.2, 00:00:00:00:02:02);
arpq_h3 :: ARPQuerier(192.168.123.1, 00:00:00:00:02:03);
arpq_h4 :: ARPQuerier(192.168.123.2, 00:00:00:00:02:04);
arpq_s1 :: ARPQuerier(192.168.124.1, 00:00:00:00:02:05);
arpq_s2 :: ARPQuerier(192.168.124.2, 00:00:00:00:02:06);
arpq_s3 :: ARPQuerier(192.168.124.3, 00:00:00:00:02:07);

t :: Tee(7);
c0[1] -> t;
c1[1] -> t;
t[0] -> [1]arpq_s1;
t[1] -> [1]arpq_s2;
t[2] -> [1]arpq_s3;
t[3] -> [1]arpq_h1;
t[4] -> [1]arpq_h2;
t[5] -> [1]arpq_h3;
t[6] -> [1]arpq_h4;

arpq_s1 -> net0out;
arpq_s2 -> net0out;
arpq_s3 -> net0out;
arpq_h1 -> net1out;
arpq_h2 -> net1out;
arpq_h3 -> net1out;
arpq_h4 -> net1out;

arpr0 :: ARPResponder(192.168.124.1 00:00:00:00:02:05, 192.168.124.2 00:00:00:00:02:06, 192.168.124.3 00:00:00:00:02:07);
arpr1 :: ARPResponder(192.168.122.1 00:00:00:00:02:01, 192.168.122.2 00:00:00:00:02:02, 192.168.123.1 00:00:00:00:02:03, 192.168.123.2 00:00:00:00:02:04);
c0[0] -> arpr0 -> net0out;
c1[0] -> arpr1 -> net1out;

rt :: StaticIPLookup(
	192.168.122.1 0,
	192.168.122.2 1,
  192.168.123.1 2,
  192.168.123.2 3,
	192.168.124.1 4,
  192.168.124.2 5,
  192.168.124.3 6);

ip :: Strip(14) -> CheckIPHeader(INTERFACES 192.168.122.1/24 192.168.122.2/24 192.168.123.1/24 192.168.123.2/24 192.168.124.1/24 192.168.124.2/24 192.168.124.3/24) -> [0]rt;
c0[2] -> ip;
c1[2] -> ip;

ips :: IPClassifier(
    src ip 192.168.124.1,
    src ip 192.168.124.2,
    src ip 192.168.124.3,
    -);

ipc :: IPClassifier(
	  src ip 192.168.122.1,
    src ip 192.168.122.2,
    src ip 192.168.123.1,
    src ip 192.168.123.2,
    -);

rt[0] -> DropBroadcasts -> FixIPSrc(192.168.122.1) -> ips;
rt[1] -> DropBroadcasts -> FixIPSrc(192.168.122.2) -> ips;
rt[2] -> DropBroadcasts -> FixIPSrc(192.168.123.1) -> ips;
rt[3] -> DropBroadcasts -> FixIPSrc(192.168.123.2) -> ips;
rt[4] -> DropBroadcasts -> FixIPSrc(192.168.124.1) -> ipc;
rt[5] -> DropBroadcasts -> FixIPSrc(192.168.124.2) -> ipc;
rt[6] -> DropBroadcasts -> FixIPSrc(192.168.124.3) -> ipc;

ips[0] -> [0]arpq_s1;
ips[1] -> [0]arpq_s2;
ips[2] -> [0]arpq_s3;
ips[3] -> Discard();

ipc[0] -> [0]arpq_h1;
ipc[1] -> [0]arpq_h2;
ipc[2] -> [0]arpq_h3;
ipc[3] -> [0]arpq_h4;
ipc[4] -> Discard();