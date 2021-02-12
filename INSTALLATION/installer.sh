#!/bin/bash

if [ $(id -u) != 0 ]; then
    echo "You're not root"
else
	echo "1 of 12 - Installing Sudoers..."
	apt-get install -y sudo
	echo "2 of 12 - Installing Bridge Utils..."
	apt-get install -y bridge-utils
	echo "3 of 12 - Installing Net Tools..."
	apt-get install -y net-tools
	echo "4 of 12 - Installing Git..."
	apt-get install -y git
	echo "5 of 12 - Installing Phython 2.7..."
	apt-get install -y python2.7
	echo "6 of 12 - Installing Pip 2.7..."
	python2.7 get-pip.py
	echo "7 of 12 - Installing Python Requests..."
	pip2.7 install requests
	echo "8 of 12 - Installing Qemu KVM..."
	apt-get install -y qemu-kvm 
	echo "9 of 12 - Installing Qemu System..."
	apt-get install -y qemu-system
	echo "10 of 12 - Installing Lib Virt..."
	apt-get install -y libvirt-bin
	echo "11 of 12 - Installing Virt Manager..."
	apt-get install -y virt-manager
	echo "12 of 12 - Installing Mininet..."
	apt-get install -y mininet

	echo 'Your system must reboot - do it now? (y/n)' && read x && [[ "$x" == "y" ]] && /sbin/reboot;
fi

