//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_ID:d518ab40-9270-432a-bfc9-929a5c6ec019
//VNF_PROVIDER:UFSM
//VNF_NAME: Shaper
//VNF_RELEASE_DATE:2017-04-08 21-45-45
//VNF_RELEASE_VERSION:1.0
//VNF_RELEASE_LIFESPAN:2017-06-08 21-45
//VNF_DESCRIPTION: Limits UDP packet rate

//Shapes UDP packet rate to no more than 500 pkt/s

in0 :: FromDPDKDevice(0);
out0 :: ToDPDKDevice(0);

in1 :: FromDPDKDevice(1);
out1 :: ToDPDKDevice(1);

cw :: Classifier(
    12/0806, //ARP to cw[0] 
    12/0800, //IP to cw[1]
    -        //Everything else is discarded
);

f :: IPClassifier(
    udp,       //UDP Packets to f[0]
    -   //Everything else pass-through
);

spl :: RatedSplitter(200); //Allows no more than 200 pkt/s

in0 -> cw; //in0 goes to classifier

cw[0] -> CheckARPHeader(14) -> out1;    //ARP packets pass-through
cw[1] -> CheckIPHeader(14) -> f;        //IP packets to IP classifier
cw[2] -> Discard; //If packet is neither ARP nor IP it is discarded

f[0] -> spl;   //UDP packets goes to splitter
f[1] -> out1;

spl[0] -> out1;
spl[1] -> Discard();

in1 -> out0; //in1 pass-through to out0
