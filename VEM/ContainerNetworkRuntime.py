from os import devnull
from subprocess import call, check_output
from subprocess import STDOUT


FNULL = open(devnull, 'w')


def check_output_text(cmd):
    data = check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class ContainerNetworkRuntime:
    def interface_exists(self, interface_id):
        return call(['ip', 'link', 'show', interface_id], stdout=FNULL, stderr=STDOUT) == 0

    def delete_interface(self, interface_id):
        if self.interface_exists(interface_id):
            call(['ip', 'link', 'del', interface_id], stdout=FNULL, stderr=STDOUT)

    def container_pid(self, container):
        container.reload()
        return str(container.attrs['State']['Pid'])

    def setup_interfaces(self, container, interfaces):
        pid = self.container_pid(container)
        for index, iface in enumerate(interfaces):
            host_iface = iface['ID']
            container_iface = 'eth' + str(index)
            peer_iface = host_iface[:11] + 'p' + str(index)

            self.delete_interface(host_iface)
            self.delete_interface(peer_iface)
            call(['ip', 'link', 'add', host_iface, 'type', 'veth', 'peer', 'name', peer_iface], stdout=FNULL, stderr=STDOUT)
            call(['ip', 'link', 'set', host_iface, 'up'], stdout=FNULL, stderr=STDOUT)
            call(['ip', 'link', 'set', peer_iface, 'netns', pid], stdout=FNULL, stderr=STDOUT)
            call(['nsenter', '-t', pid, '-n', 'ip', 'link', 'set', peer_iface, 'name', container_iface], stdout=FNULL, stderr=STDOUT)
            call(['nsenter', '-t', pid, '-n', 'ip', 'link', 'set', 'dev', container_iface, 'address', iface['MAC']], stdout=FNULL, stderr=STDOUT)
            call(['nsenter', '-t', pid, '-n', 'ip', 'link', 'set', container_iface, 'up'], stdout=FNULL, stderr=STDOUT)
            if iface.get('IP') is not None:
                call(['nsenter', '-t', pid, '-n', 'ip', 'addr', 'add', iface['IP'], 'dev', container_iface], stdout=FNULL, stderr=STDOUT)

    def release_interfaces(self, interfaces):
        for iface in interfaces:
            self.delete_interface(iface['ID'])


DEFAULT_CONTAINER_NETWORK_RUNTIME = ContainerNetworkRuntime()
