#!/bin/bash
#USAGE: source Client_DNS.sh int_ip_iface int_ip faults_tolerated sc_ext_ip_1 ... sc_ext_ip_n

sc_ips=""
for ip in ${@:3};
do
    sc_ips="${sc_ips} ${ip}"
done

curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $1 $2
	ip route add default dev $1
	cd ${BASH_REMATCH[1]}/DSN-2023/SFC-FT_DNS/
	python3 DNS_Client.py $sc_ips
else
	python3 DNS_Client.py $sc_ips
fi
