from os import devnull
from subprocess import call, check_output, run
from subprocess import PIPE, STDOUT


FNULL = open(devnull, 'w')


class ContainerNetworkError(RuntimeError):
    def __init__(self, operation, interface_id, command, output):
        self.operation = operation
        self.interface_id = interface_id
        self.command = command
        self.output = output
        super().__init__(
            "Container network operation failed; operation="
            + operation
            + "; interface="
            + str(interface_id)
            + "; command="
            + " ".join(command)
            + (("; output=" + output.strip()) if output.strip() else "")
        )


def check_output_text(cmd):
    data = check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class ContainerNetworkRuntime:
    def run_checked(self, operation, interface_id, command):
        completed = run(command, stdout=PIPE, stderr=STDOUT, text=True)
        if completed.returncode != 0:
            raise ContainerNetworkError(operation, interface_id, command, completed.stdout)
        return completed.stdout

    def interface_exists(self, interface_id):
        return call(['ip', 'link', 'show', interface_id], stdout=FNULL, stderr=STDOUT) == 0

    def delete_interface(self, interface_id):
        if self.interface_exists(interface_id):
            self.run_checked("delete", interface_id, ['ip', 'link', 'del', interface_id])

    def container_pid(self, container):
        container.reload()
        pid = container.attrs.get('State', {}).get('Pid', 0)
        if not isinstance(pid, int) or pid <= 0:
            raise ContainerNetworkError("inspect_namespace", "unknown", [], "Container has no active network namespace")
        return str(pid)

    def setup_interfaces(self, container, interfaces):
        pid = self.container_pid(container)
        for index, iface in enumerate(interfaces):
            host_iface = iface['ID']
            container_iface = 'eth' + str(index)
            peer_iface = host_iface[:11] + 'p' + str(index)

            self.delete_interface(host_iface)
            self.delete_interface(peer_iface)
            self.run_checked("create_veth", host_iface, ['ip', 'link', 'add', host_iface, 'type', 'veth', 'peer', 'name', peer_iface])
            self.run_checked("enable_host_interface", host_iface, ['ip', 'link', 'set', host_iface, 'up'])
            self.run_checked("move_to_namespace", host_iface, ['ip', 'link', 'set', peer_iface, 'netns', pid])
            self.run_checked("rename_container_interface", host_iface, ['nsenter', '-t', pid, '-n', 'ip', 'link', 'set', peer_iface, 'name', container_iface])
            self.run_checked("set_container_mac", host_iface, ['nsenter', '-t', pid, '-n', 'ip', 'link', 'set', 'dev', container_iface, 'address', iface['MAC']])
            self.run_checked("enable_container_interface", host_iface, ['nsenter', '-t', pid, '-n', 'ip', 'link', 'set', container_iface, 'up'])
            if iface.get('IP') is not None:
                self.run_checked("set_container_ip", host_iface, ['nsenter', '-t', pid, '-n', 'ip', 'addr', 'add', iface['IP'], 'dev', container_iface])

    def release_interfaces(self, interfaces):
        for iface in interfaces:
            self.delete_interface(iface['ID'])


DEFAULT_CONTAINER_NETWORK_RUNTIME = ContainerNetworkRuntime()
