NIEP: NFV Infrastructure Emulation Platform
========================================================

*Status: Beta -- Version: 1.1*

### What is NIEP?

NIEP uses the Mininet[1] and Click-on-OSv[2] to deploy a complete emulated 
infrastructure based on full virtualization NFV paradigm. It can be used to
define single VNFs instantiation as well as large SFCs linked to mininet hosts 
and SDN switches. The NIEP is especially indicating to test the behavior of
NFV topologies and collect results similar to a real scenario.<br/> 

The NIEP provides several elements to create your topology:

1. Mininet Hosts - based on process virtualization, it emulates a functional host in the topology.<br/>
2. Mininet Common Switches - adapted from Mininet OvSwitch, it creates a virtual switch with a controller
that simulates the packet forwarding of a common switch.<br/>
3. Mininet OvS - Open vSwitch emulation with an external controller (NIEP natively provides POX in the repository,
but others can be also used).<br/>
4. Mininet Links - used to connect mininet elements with other mininet elements.<br/>
5. TinyCore 12 VMs - generic minimalist linux distribution, natively acessible using SSH (Username: tc / Password: NIEPvm00).<br/>
5. Click-on-OSv VNFs - platform to execute Click functions, it natively provides an EMS to control the VNF lifecvyle.<br/>
6. CLick-on-OSv Links - created to connect Click-on-OSv elements with other Click-on-OSv elements and Click-on-OSv 
elements with Mininet elements.<br/>

NIEP topologies are created using a simple JSON model (some examples are in the 'EXAMPLES' folder), there are three components to be described:

1. VNFs - describe Click-on-OSv VM ID and requisites (memory, cpu, management interface and other interfaces), this description can be used both by SFC component and topology component.<br/>
2. SFCs - describe the relationship between VNFs to compose a service with a incoming data point (IP) and outgoing data points (OPs) and VNFs connections (in this case, all the predefined VNFs interfaces are ignored except the management interface).<br/>
3. Topologies - describe the mininet elements and their relationship with VNFs and SFCs.<br/>

A installer for NIEP dependencies is available in the 'INSTALLATION' folder 
named as 'installer.sh'. Please, make sure that your CPU has support for virtualization
technology and it is enabled. <br/>

For the platform execution, in NIEP folder, execute 'python CLI/CLI.py' (use
'help' command in the NIEP CLI to show the platform functionalities).

You can see a brief tutorial about NIEP installation and usage [HERE](https://docs.google.com/presentation/d/e/2PACX-1vSuS-3_7BMIaioXhqmlGuGkvf36IZvKu8GRQnOle1gYHUOwGxcnAroJi5Y5dJQ4oGABe7uf5RN5GzBw/pub?start=false&loop=false&delayms=3000).

### How does it was created?

The NIEP platform was developed using python 2.7 language and many other
applications below:

1. General programs<br/>
1.1 Sudoers (apt-get install sudo)<br/>
1.2 Bridge Utils (apt-get install bridge-utils)<br/>
1.3 Net Tools (apt-get install net-tools)<br/>
1.4 SSH Pass (apt-get install sshpass) <br/>
1.5 Git (apt-get install git)<br/>
1.6 GIT LFS (http://arfc.github.io/manual/guides/git-lfs)<br/>
2. Python<br/>
2.1 Python 2.7.9 (apt-get install python2.7)<br/>
2.2 Pip (apt-get install python-pip)<br/>
2.3 Requests (pip install requests)<br/>
3. Hypervisor<br/>
3.1 Qemu (apt-get install qemu-kvm qemu-system)<br/>
3.2 Libvirt 1.2.9 (apt-get install libvirt-bin)<br/>
3.3 Virt Manager - Optional - (apt-get install virt-manager)<br/>
4. Mininet<br/>
4.1 Mininet 2.3.0d1 (https://github.com/mininet/mininet.git)<br/> 

### Next Steps

1. Native support to COVEN [3] VNF platform<br/>
2. Native support to HoLMES [4] EMS solution<br/>
3. Stable distributed mode (NIEP agent)<br/> 
4. Assisted creation for NIEP Topologies, SFCs and VNFs<br/>
5. Topology structure viewer<br/>
6. NIEP working as an API (NIEP Module)<br/>
7. Graphical interface

### Support

Contact us towards git issues requests or by the e-mail vfulber@inf.ufsm.br.

### NIEP Research Group

Vinícius Fülber Garcia (UFPR - Brazil)<br/>
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

### Publications

T. Tavares, L. Marcuzzo, V. Fulber-Garcia, G. Venâncio, M. Franco, L. Bondan, F. De Turk, L. Granville, E. Duarte, C. Santos and A. Schaeffer-filho, "NIEP - NFV Infrastructure Emulation Platform", in 32nd IEEE AINA, Cracow, Poland, 2018.
<br/>
V. Fulber-Garcia, T. Tavares, L. Marcuzzo, G. Venâncio, M. Franco, L. Bondan, A. Schaeffer-Filho, C. Santos, F. De Turck, L. Granville, E. Duarte, "On the Design and Development of Emulation Platforms for NFV-based Infrastructures", in International Journal of Grid and Utility Computing (IJGUC), 11(2). 2020.

### References

[1] B. Lantz, B. Heller and N. McKeown, "A network in a laptop: rapid prototyping for software-defined networks", in 9th ACM SIGCOMM Workshop on Hot Topics in Networks (Hotnets-IX), Monterey, California, 2010, p. 6. doi=10.1145/1868447.1868466
<br/>
[2] L. da Cruz Marcuzzo et al., "Click-on-OSv: A platform for running Click-based middleboxes", 2017 IFIP/IEEE Symposium on Integrated Network and Service Management (IM), Lisbon, 2017, pp. 885-886. doi: 10.23919/INM.2017.7987396
<br/>
[3] V. Fulber-Garcia, et al. "On the design of a flexible architecture for virtualized network function platforms", 2019 IEEE Global Communications Conference (GLOBECOM). Waikoloa, 2019, pp. 1-6. doi: 10.1109/GLOBECOM38437.2019.9013111
<br/>
[4] https://github.com/ViniGarcia/HoLMES
<br/>
[5] V. F. Garcia et al., "PyCOO: Uma API em Python para Plataforma Click-On-Osv", 2017 Escola Regional de Redes de Computadores (ERRC), Santa Maria, 2017, pp. 119-126. 