#!/bin/bash
#USAGE: source SC.sh ext_ip_iface ext_ip int_ip

curr_folder=$(pwd)
if [[ $curr_folder =~ (.+)"/CLI"(.*) ]];
then
	ifconfig $1 $2
	ip route add default dev $1
	cd ${BASH_REMATCH[1]}/SBRC-2022/SFC-FT_Components/
	python3 SC.py $2 $3
else
	python3 SC.py $2 $3
fi

