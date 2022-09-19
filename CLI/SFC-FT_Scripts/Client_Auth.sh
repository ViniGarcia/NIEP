#!/bin/bash
#USAGE: source Client.sh priv_key_file pub_key_file int_ip_iface int_ip faults_tolerated sc_ext_ip_1 ... sc_ext_ip_n

client_args=$1" "$2" "
for ip in ${@:5};
do
    client_args="${client_args} ${ip}"
done
curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $3 $4
	ip route add default dev $3
	cd ${BASH_REMATCH[1]}/SBRC-2022/SFC-FT_DNS/
	python3 DNS_Client_Auth.py $client_args
else
	python3 DNS_Client_Auth.py $client_args
fi
