//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_ID:6adb06e8-2cfb-491a-bebd-f5cb87830b28
//VNF_PROVIDER:UFSM
//VNF_NAME:Forward
//VNF_RELEASE_DATE:2017-04-08 21-45-45
//VNF_RELEASE_VERSION:1.0
//VNF_RELEASE_LIFESPAN:2017-06-08 21-45
//VNF_DESCRIPTION: Forward between two ports
FromDPDKDevice(0) -> ToDPDKDevice(1);
FromDPDKDevice(1) -> ToDPDKDevice(0);
