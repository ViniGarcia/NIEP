#!/bin/bash

if [ $(id -u) != 0 ]; then
    echo "You're not root"
else
	echo "1 of 13 - Installing Sudoers..."
	apt-get install -y sudo
	echo "2 of 13 - Installing Bridge Utils..."
	apt-get install -y bridge-utils
	echo "3 of 13 - Installing Net Tools..."
	apt-get install -y net-tools
	echo "4 of 13 - Installing SSH Pass..."
	apt-get install -y sshpass
	echo "5 of 13 - Installing Git..."
	apt-get install -y git
	echo "6 of 13 - Installing Phython 2.7..."
	apt-get install -y python2.7
	echo "7 of 13 - Installing Pip 2.7..."
	python2.7 get-pip.py
	echo "8 of 13 - Installing Python Requests..."
	pip2.7 install requests
	echo "9 of 13 - Installing Qemu KVM..."
	apt-get install -y qemu-kvm 
	echo "10 of 13 - Installing Qemu System..."
	apt-get install -y qemu-system
	echo "11 of 13 - Installing Lib Virt..."
	apt-get install -y libvirt-bin
	echo "12 of 13 - Installing Virt Manager..."
	apt-get install -y virt-manager
	echo "13 of 13 - Installing Mininet..."
	apt-get install -y mininet

	echo 'Your system must reboot - do it now? (y/n)' && read x && [[ "$x" == "y" ]] && /sbin/reboot;
fi

