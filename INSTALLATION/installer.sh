#!/bin/bash

if [ $(id -u) != 0 ]; then
    echo "You're not root"
else
	echo "1 of 17 - Installing Sudoers..."
	apt-get install -y sudo
	echo "2 of 17 - Installing Bridge Utils..."
	apt-get install -y bridge-utils
	echo "3 of 17 - Installing Net Tools..."
	apt-get install -y net-tools
	echo "4 of 17 - Installing IP Route 2..."
	apt-get install iproute2
	echo "5 of 17 - Installing SSH Pass..."
	apt-get install -y sshpass
	echo "6 of 17 - Installing Git..."
	apt-get install -y git
	echo "7 of 17 - Installing Phython 2.7..."
	apt-get install -y python2.7
	echo "8 of 17 - Installing Pip 2.7..."
	python2.7 get-pip.py
	echo "9 of 17 - Installing Python Requests..."
	pip2.7 install requests
	echo "10 of 17 - Installing Qemu KVM..."
	apt-get install -y qemu-kvm 
	echo "11 of 17 - Installing Qemu System..."
	apt-get install -y qemu-system
	echo "12 of 17 - Installing Lib Virt..."
	apt-get install -y libvirt-bin
	echo "13 of 17 - Installing Virt Manager..."
	apt-get install -y virt-manager
	echo "14 of 17 - Installing Mininet..."
	apt-get install -y mininet
	echo "15 of 17 - Installing Flask..."
	pip2.7 install flask
	echo "16 of 17 - Installing PSUtil..."
	pip2.7 install psutil
	echo "17 of 17 - Installing IPAddress..."
	pip2.7 install ipaddress

	echo "Addon 1 of 1 - Installing Git LFS..."
	mkdir git-lfs
	cd git-lfs
	wget https://github.com/git-lfs/git-lfs/releases/download/v2.9.0/git-lfs-linux-amd64-v2.9.0.tar.gz
	tar -xf git-lfs-linux-amd64-v2.9.0.tar.gz
	chmod 755 install.sh
	./install.sh
	cd ..
	rm -r git-lfs

	echo 'Your system must reboot - do it now? (y/n)' && read x && [[ "$x" == "y" ]] && /sbin/reboot;
fi

