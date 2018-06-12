#!/bin/bash

if [ $(id -u) != 0 ]; then
    echo "You're not root"
else
	echo "1 of 12 - Installing Sudoers..."
	apt-get install sudo
	echo "2 of 12 - Installing Bridge Utils..."
	apt-get install bridge-utils
	echo "3 of 12 - Installing Net Tools..."
	apt-get install net-tools
	echo "4 of 12 - Installing Git..."
	apt-get install git
	echo "5 of 12 - Installing Phython 2.7..."
	apt-get install python2.7
	echo "6 of 12 - Installing Pip 2.7..."
	python2.7 get-pip.py
	echo "7 of 12 - Installing Python Requests..."
	pip2.7 install requests
	echo "8 of 12 - Installing Qemu KVM..."
	apt-get install qemu-kvm 
	echo "9 of 12 - Installing Qemu System..."
	apt-get install qemu-system
	echo "10 of 12 - Installing Lib Virt..."
	apt-get install libvirt-bin
	echo "11 of 12 - Installing Virt Manager..."
	apt-get install virt-manager
	echo "12 of 12 - Installing Mininet..."
	git clone git://github.com/mininet/mininet
	cd mininet
	git tag
	git checkout -b 2.3.0d1
	cd ..
	mininet/util/install.sh -a

	echo 'Your system must reboot - do it now? (y/n)' && read x && [[ "$x" == "y" ]] && /sbin/reboot
fi

