#!/bin/bash
#USAGE: source Auth_NF.sh int_ip_iface int_ip priv_key_file

curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $1 $2
	ip route add default dev $1
	cd ${BASH_REMATCH[1]}/DSN-2023/SFC-FT_DNS/
	python3 Auth_NF.py $2 $3
else
	python3 Auth_NF.py $2 $3
fi
