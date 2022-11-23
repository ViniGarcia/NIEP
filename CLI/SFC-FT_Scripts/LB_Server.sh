#!/bin/bash
#USAGE: source LB_Server.sh int_ip_iface int_ip faults_tolerated

curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $1 $2
	ip route add default dev $1
	cd ${BASH_REMATCH[1]}/DSN-2023/SFC-FT_LB/
	python3 Server.py $1 $3 1
else
	python3 Server.py $1 $3 1
fi
