from os import devnull
from os.path import abspath
from signal import signal, SIGINT, SIG_IGN
from subprocess import call, check_output, Popen
from subprocess import STDOUT
from sys import executable
from time import sleep


FNULL = open(devnull, 'w')


def pre_exec():
    signal(SIGINT, SIG_IGN)


def check_output_text(cmd):
    data = check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class InfrastructureRuntime:
    def interfaces_mapping(self):
        ifacesDictionary = {}

        ifacesData = check_output_text(['brctl', 'show']).split('\n')
        for iface in ifacesData[1:-1]:
            iface = iface.split('\t')
            if len(iface) > 5:
                ifacesDictionary[iface[0]] = iface[5]

        return ifacesDictionary

    def bridge_exists(self, bridgeID):
        ifacesData = check_output_text(['brctl', 'show']).split('\n')
        for iface in ifacesData:
            if iface.startswith(bridgeID):
                return True
        return False

    def ensure_bridge(self, bridgeID):
        if not self.bridge_exists(bridgeID):
            call(['brctl', 'addbr', bridgeID], stdout=FNULL, stderr=STDOUT)

    def ensure_virt_network(self, networkID, configPath):
        netData = check_output_text(['virsh', 'net-list']).split('\n')
        for net in netData:
            netColumns = net.split()
            if netColumns and netColumns[0] == networkID:
                if len(netColumns) < 2 or netColumns[1] != 'active':
                    call(['virsh', 'net-start', networkID], stdout=FNULL, stderr=STDOUT)
                return
        call(['virsh', 'net-create', configPath], stdout=FNULL, stderr=STDOUT)

    def start_local_pox(self):
        poxPath = '/'.join(abspath(__file__).split('/')[:-2]) + '/OFCONTROLLERS/pox/pox.py'
        process = Popen([executable, poxPath, 'forwarding.l2_learning'], stdout=FNULL, stderr=STDOUT, preexec_fn=pre_exec)
        sleep(3)
        return process

    def stop_process(self, process):
        if process is not None:
            process.terminate()

    def destroy_virt_network(self, networkID):
        call(['virsh', 'net-destroy', networkID], stdout=FNULL, stderr=STDOUT)

    def remove_bridge(self, bridgeID):
        call(['ifconfig', bridgeID, 'down'], stdout=FNULL, stderr=STDOUT)
        call(['brctl', 'delbr', bridgeID], stdout=FNULL, stderr=STDOUT)

    def prepare_topology_infrastructure(self):
        self.ensure_bridge('vbrNIEP')
        self.ensure_virt_network('vnNIEP', '../CONFS/vnNIEP.xml')

    def cleanup_topology_infrastructure(self):
        self.destroy_virt_network('vnNIEP')
        self.remove_bridge('vbrNIEP')


DEFAULT_INFRASTRUCTURE_RUNTIME = InfrastructureRuntime()
