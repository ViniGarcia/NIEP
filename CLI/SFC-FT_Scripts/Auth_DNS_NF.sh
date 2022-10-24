#!/bin/bash
#USAGE: source DNS_NF.sh server_privkey_file int_ip_iface int_ip 

curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $2 $3
	ip route add default dev $2
	cd ${BASH_REMATCH[1]}/DSN-2023/SFC-FT_DNS/
	python3 Auth_DNS_NF.py $1 $3
else
	python3 Auth_DNS_NF.py $1 $3
fi
