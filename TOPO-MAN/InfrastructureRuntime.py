from os import devnull
from os.path import abspath, dirname, join
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
    def __init__(self):
        # Keep the two infrastructure resources independent.  A bridge can be
        # removed even when libvirt reports an error (and vice versa), and a
        # retry must only revisit the operation that did not complete.
        self._CLEANUP_COMPLETED = set()
        self.CLEANUP_ERRORS = []

    def interfaces_mapping(self):
        ifacesDictionary = {}

        ifacesData = check_output_text(['brctl', 'show']).split('\n')
        for iface in ifacesData[1:-1]:
            iface = iface.split('\t')
            if len(iface) > 5:
                ifacesDictionary[iface[0]] = iface[5]

        linkData = check_output_text(['ip', '-o', 'link', 'show']).split('\n')
        for link in linkData:
            linkColumns = link.split(': ')
            if len(linkColumns) >= 2:
                linkName = linkColumns[1].split('@')[0]
                ifacesDictionary.setdefault(linkName, linkName)

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
            if hasattr(process, 'poll') and process.poll() is not None:
                return
            process.terminate()

    def destroy_virt_network(self, networkID):
        activeNetworks = check_output_text(['virsh', 'net-list', '--name']).splitlines()
        if networkID not in activeNetworks:
            return
        status = call(['virsh', 'net-destroy', networkID], stdout=FNULL, stderr=STDOUT)
        if status != 0:
            raise RuntimeError(
                "virsh net-destroy failed for " + str(networkID) + " with status " + str(status)
            )

    def remove_bridge(self, bridgeID):
        if not self.bridge_exists(bridgeID):
            return
        errors = []
        status = call(['ifconfig', bridgeID, 'down'], stdout=FNULL, stderr=STDOUT)
        if status != 0:
            errors.append("ifconfig down returned " + str(status))
        status = call(['brctl', 'delbr', bridgeID], stdout=FNULL, stderr=STDOUT)
        if status != 0:
            errors.append("brctl delbr returned " + str(status))
        if errors:
            raise RuntimeError(" | ".join(errors))

    def prepare_topology_infrastructure(self):
        self._CLEANUP_COMPLETED = set()
        self.CLEANUP_ERRORS = []
        self.ensure_bridge('vbrNIEP')
        configPath = join(dirname(abspath(__file__)), '..', 'CONFS', 'vnNIEP.xml')
        self.ensure_virt_network('vnNIEP', configPath)

    def cleanup_topology_infrastructure(self):
        completed = getattr(self, '_CLEANUP_COMPLETED', None)
        if completed is None:
            completed = set()
            self._CLEANUP_COMPLETED = completed

        cleanupErrors = []
        networkKey = ('libvirt_network', 'vnNIEP', 'destroy')
        if networkKey not in completed:
            try:
                status = self.destroy_virt_network('vnNIEP')
                if status not in (0, None):
                    raise RuntimeError(
                        "destroy returned status " + str(status)
                    )
            except Exception as exc:
                cleanupErrors.append({
                    "resource_type": "libvirt_network",
                    "resource_id": "vnNIEP",
                    "operation": "destroy",
                    "message": str(exc),
                })
            else:
                completed.add(networkKey)

        bridgeKey = ('bridge', 'vbrNIEP', 'remove')
        if bridgeKey not in completed:
            try:
                status = self.remove_bridge('vbrNIEP')
                if status not in (0, None):
                    raise RuntimeError(
                        "remove returned status " + str(status)
                    )
            except Exception as exc:
                cleanupErrors.append({
                    "resource_type": "bridge",
                    "resource_id": "vbrNIEP",
                    "operation": "remove",
                    "message": str(exc),
                })
            else:
                completed.add(bridgeKey)

        self.CLEANUP_ERRORS = cleanupErrors
        return -10 if cleanupErrors else 0


DEFAULT_INFRASTRUCTURE_RUNTIME = InfrastructureRuntime()
