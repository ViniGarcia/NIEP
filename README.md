NIEP: NFV Infrastructure Emulation Platform
========================================================

### What is NIEP?

NIEP uses the Mininet[1] and Click-on-OSv[2] to deploy a complete emulated 
infrastructure based on full virtualization NFV paradigm. It can be used to
define single VNFs instantiation as well as large SFCs linked to mininet hosts 
and SDN switches. The NIEP is especially indicating to test the behavior of
NFV topologies and collect results similar to a real scenario.  


### How does it was created?

The NIEP platform was developed using python 2.7 language and many other
applications below:

1. General programs
..* Sudoers (apt-get install sudo)
..* Bridge Utils (apt-get install bridge-utils)
..* Net Tools (apt-get install net-tools)
..* Git (apt-get install git)
2. Python
..* Python 2.7.9 (apt-get install -t jessie python2.7)
..* Pip (apt-get install python-pip)
..* Requets (pip install requests)
3. Hypervisor
..* Qemu (apt-get install qemu-kvm)
..* Libvirt 1.2.9 (apt-get install libvirt-bin)
..* Virt Manager - Optional - (apt-get install virt-manager)
4. Mininet
..* Mininet 2.3.0d1 ()

Actually, there is no installer for NIEP - in progress - to execute
it you should (in the NIEP folder) execute 'python CLI/CLI.py'.  

### Support

Contact us towards git issues requests or by the e-mail vfulber@inf.ufsm.br.

### Group

Vinícius Fülber Garcia
Thales Nicolai Tavares
Leonardo da Cruz Marcuzzo
Giovanni Venâncio de Souza
Muriel Figueredo Franco
Lucas Bondan
Filip De Turck
Lisandro Zambenedetti Granville
Elias Procópio Duarte Junior
Carlos Raniery Paula dos Santos
Alberto Egon Schaeffer-Filho

### Citations

-> Mininet <-
[1] B. Lantz, B. Heller and N. McKeown, "A network in a laptop: rapid prototyping for software-defined networks", in 9th ACM SIGCOMM Workshop on Hot Topics in Networks (Hotnets-IX), Monterey, California, 2010, p. 6. doi=10.1145/1868447.1868466

-> Click-On-OSv <-
[2] L. da Cruz Marcuzzo et al., "Click-on-OSv: A platform for running Click-based middleboxes," 2017 IFIP/IEEE Symposium on Integrated Network and Service Management (IM), Lisbon, 2017, pp. 885-886. doi: 10.23919/INM.2017.7987396