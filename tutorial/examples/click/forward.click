//VNF_HEADER
//VNF_VERSION: 1.0
//VNF_NAME: Forward
//VNF_DESCRIPTION: Forward every packet between two Click-on-OSv data ports

FromDPDKDevice(0) -> ToDPDKDevice(1);
FromDPDKDevice(1) -> ToDPDKDevice(0);
