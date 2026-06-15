NIEP: NFV Infrastructure Emulation Platform
========================================================

*Status: Beta -- Version: 1.1 -- Python 3 port*

### What is NIEP?

NIEP uses Mininet[1], libvirt/KVM, Docker, and Click-on-OSv[2] to deploy an emulated NFV infrastructure. It can instantiate single VNFs, Docker containers, and larger SFCs connected to Mininet hosts and SDN switches. NIEP is useful for testing NFV topologies and collecting results in a controlled environment similar to a real deployment.<br/>

The NIEP provides several elements to create your topology:

1. Mininet Hosts - based on process virtualization, they emulate functional hosts in the topology.<br/>
2. Mininet Common Switches - adapted from Mininet OvSwitch, they create virtual switches with a controller that simulates common switch forwarding.<br/>
3. Mininet OvS - Open vSwitch emulation with an external controller. NIEP ships a Python 3 compatible POX tree in the repository, but other controllers can also be used.<br/>
4. Mininet Links - used to connect Mininet elements with other Mininet elements.<br/>
5. TinyCore 12 VMs - generic minimalist Linux distribution, accessible over SSH (username: tc / password: NIEPvm00).<br/>
6. Click-on-OSv VNFs - platform to execute Click functions. It provides an EMS to control the VNF lifecycle.<br/>
7. Click-on-OSv Links - created to connect Click-on-OSv elements with other Click-on-OSv elements and Click-on-OSv elements with Mininet elements.<br/>
8. Docker Containers - lightweight compute endpoints attached to Mininet through veth interfaces.<br/>

NIEP topologies are created using a simple JSON model. The maintained runnable examples are in the `tutorial/examples/` directory. There are three components to describe:

1. VNFs - describe Click-on-OSv VM ID and requirements such as memory, CPU, management interface, and data interfaces. This description can be used by both SFC and topology components.<br/>
2. SFCs - describe the relationship between VNFs to compose a service with an incoming point (IP), outgoing points (OPs), and VNF connections. In this case, all predefined VNF interfaces are ignored except the management interface.<br/>
3. Containers - describe Docker image, command, privileges, and data interfaces.<br/>
4. Topologies - describe Mininet elements and their relationship with VMs, containers, VNFs and SFCs.<br/>

### Quick Start

The recommended development environment is the Vagrant VM. It provisions the same Python 3 dependency set used by the manual installer.

```bash
make vm-up
make vm-cli
```

Inside the NIEP prompt, load a tutorial example:

```text
niep> define ../tutorial/examples/mininet-ping.json
niep> topoup
niep> mininet
mininet> pingall
```

Manual installation is also available:

```bash
sudo ./INSTALLATION/installer.sh --repo "$PWD" --user "$USER"
```

The installer delegates to `INSTALLATION/provision-vm.sh`, which is also used by Vagrant. Make sure your CPU supports hardware virtualization and that it is enabled in the host firmware.

Run NIEP from the `CLI/` directory:

```bash
cd CLI
sudo python3 CLI.py
```

See the sequential tutorial in [`tutorial/README.md`](tutorial/README.md).

Run the static checks on the host:

```bash
make test-static
```

Run the structured integration tests inside the Vagrant VM:

```bash
make vm-test-integration
```

NIEP can also be operated non-interactively through a local Unix socket:

```bash
make vm-daemon
make vm-ctl NIEPCTL_ARGS="--json status"
```

See [`tutorial/06-service-api.md`](tutorial/06-service-api.md) for the service workflow.

### How was it created?

The original NIEP platform was developed for Python 2.7. This branch ports the core emulator to Python 3 and uses the applications below:

1. General programs<br/>
1.1 Sudoers (apt-get install sudo)<br/>
1.2 Bridge Utils (apt-get install bridge-utils)<br/>
1.3 IP Route 2 (apt-get install iproute2)<br/>
1.4 Net Tools (apt-get install net-tools)<br/>
1.5 SSH Pass (apt-get install sshpass)<br/>
1.6 Git (apt-get install git)<br/>
1.7 Git LFS (https://git-lfs.com/)<br/>
2. Python<br/>
2.1 Python 3 (apt-get install python3 python3-venv python3-pip)<br/>
2.2 Python libvirt bindings (apt-get install python3-libvirt)<br/>
2.3 Requests, Flask, and psutil (installed from INSTALLATION/requirements-py3-min.txt)<br/>
3. Hypervisor<br/>
3.1 Qemu (apt-get install qemu-kvm qemu-system qemu-utils)<br/>
3.2 Libvirt (apt-get install libvirt-daemon-system libvirt-clients)<br/>
3.3 Virt Manager - Optional - (apt-get install virt-manager)<br/>
4. Mininet<br/>
4.1 Mininet (apt-get install mininet)<br/>
5. Containers<br/>
5.1 Docker Engine (apt-get install docker.io)<br/>
5.2 Docker SDK for Python (installed from INSTALLATION/requirements-py3-min.txt)<br/>
6. OpenFlow controller<br/>
6.1 POX, vendored in OFCONTROLLERS/pox and compatible with Python 3 in this branch<br/>

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
