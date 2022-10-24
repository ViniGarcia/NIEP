#!/bin/bash
#USAGE: source LB_NF.sh int_ip_iface int_ip consensus_file_path

curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $1 $2
	ip route add default dev $1
	cd ${BASH_REMATCH[1]}/DSN-2023/SFC-FT_LB/
	python3 LoadBalancer.py $2 $3
else
	python3 LoadBalancer.py $2 $3
fi
