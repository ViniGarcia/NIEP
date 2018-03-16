NIEP: NFV Infrastructure Emulation Platform
========================================================

*Status: Beta -- Version: 0.1*

### What is NIEP?

NIEP uses the Mininet[1] and Click-on-OSv[2] to deploy a complete emulated 
infrastructure based on full virtualization NFV paradigm. It can be used to
define single VNFs instantiation as well as large SFCs linked to mininet hosts 
and SDN switches. The NIEP is especially indicating to test the behavior of
NFV topologies and collect results similar to a real scenario.  


### How does it was created?

The NIEP platform was developed using python 2.7 language and many other
applications below:

1. General programs<br/>
1.1 Sudoers (apt-get install sudo)<br/>
1.2 Bridge Utils (apt-get install bridge-utils)<br/>
1.3 Net Tools (apt-get install net-tools)<br/>
1.4 Git (apt-get install git)<br/>
2. Python<br/>
2.1 Python 2.7.9 (apt-get install python2.7)<br/>
2.2 Pip (apt-get install python-pip)<br/>
2.3 Requets (pip install requests)<br/>
3. Hypervisor<br/>
3.1 Qemu (apt-get install qemu-kvm)<br/>
3.2 Libvirt 1.2.9 (apt-get install libvirt-bin)<br/>
3.3 Virt Manager - Optional - (apt-get install virt-manager)<br/>
4. Mininet<br/>
4.1 Mininet 2.3.0d1 (https://github.com/mininet/mininet.git)

Actually, there is no installer for NIEP (in progress), to use
it you should (in the NIEP folder) execute 'python CLI/CLI.py' (use
'help' command in the NIEP CLI to show the platform functionalities).  

### Next Steps

1. Native distributed mode (NIEP agent)<br/>
2. VNF-REPO (Local(OK), HDFS(OK), HTTP(IMPLEMENTING))<br/>
3. Assisted creation for NIEP Topologies, SFCs and VNFs<br/>
4. Topology structure viewer<br/>
5. NIEP working as an API (NIEP Module)<br/>
6. High level scripts for VNFs actions (PyCOO[3] based)<br/>
7. Graphical interface

### Support

Contact us towards git issues requests or by the e-mail vfulber@inf.ufsm.br.

### NIEP Research Group

Vinícius Fülber Garcia (UFSM - Brazil)<br/>
Thales Nicolai Tavares (UFSM - Brazil)<br/>
Leonardo da Cruz Marcuzzo (UFSM - Brazil)<br/>
Giovanni Venâncio de Souza (UFPR - Brazil)<br/>
Muriel Figueredo Franco (UFRGS - Brazil)<br/>
Lucas Bondan (UFRGS - Brazil)<br/>
Filip De Turck (Ghent University - Belgium)<br/>
Lisandro Zambenedetti Granville (UFRGS - Brazil)<br/>
Elias Procópio Duarte Junior (UFPR - Brazil)<br/>
Carlos Raniery Paula dos Santos (UFSM - Brazil)<br/>
Alberto Egon Schaeffer-Filho (UFRGS - Brazil)

### References

-> Mininet <-<br/>
[1] B. Lantz, B. Heller and N. McKeown, "A network in a laptop: rapid prototyping for software-defined networks", in 9th ACM SIGCOMM Workshop on Hot Topics in Networks (Hotnets-IX), Monterey, California, 2010, p. 6. doi=10.1145/1868447.1868466
<br/>
-> Click-On-OSv <-<br/>
[2] L. da Cruz Marcuzzo et al., "Click-on-OSv: A platform for running Click-based middleboxes", 2017 IFIP/IEEE Symposium on Integrated Network and Service Management (IM), Lisbon, 2017, pp. 885-886. doi: 10.23919/INM.2017.7987396
<br/>
-> PyCOO <-<br/>
[3] V. F. Garcia et al., "PyCOO: Uma API em Python para Plataforma Click-On-Osv", 2017 Escola Regional de Redes de Computadores (ERRC), Santa Maria, 2017, pp. 119-126. 