from os import devnull
from subprocess import call
from subprocess import check_output
from subprocess import STDOUT
from time import sleep


FNULL = open(devnull, 'w')


def check_output_text(cmd):
    data = check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class VMNetworkRuntime:
    def bridge_lines(self):
        return check_output_text(['brctl', 'show']).split('\n')

    def bridge_exists(self, bridgeID):
        for bridgeLine in self.bridge_lines():
            if bridgeLine.startswith(bridgeID):
                return True
        return False

    def create_bridge(self, bridgeID, mac):
        call(['brctl', 'addbr', bridgeID], stdout=FNULL, stderr=STDOUT)
        call(['ifconfig', bridgeID, "hw", "ether", mac], stdout=FNULL, stderr=STDOUT)

    def enable_bridge(self, bridgeID):
        call(['ifconfig', bridgeID, 'up'], stdout=FNULL, stderr=STDOUT)

    def disable_bridge(self, bridgeID):
        call(['ifconfig', bridgeID, 'down'], stdout=FNULL, stderr=STDOUT)

    def delete_bridge(self, bridgeID):
        call(['brctl', 'delbr', bridgeID], stdout=FNULL, stderr=STDOUT)

    def prepare_interfaces(self, interfaces):
        for iface in interfaces:
            if not self.bridge_exists(iface['ID']):
                self.create_bridge(iface['ID'], iface['LINK_MAC'])
        for iface in interfaces:
            self.enable_bridge(iface['ID'])

    def release_interfaces(self, interfaces):
        for iface in interfaces:
            self.disable_bridge(iface['ID'])
            self.delete_bridge(iface['ID'])

    def management_ip(self, managementMac):
        for attempt in range(0, 3):
            arpData = check_output_text(['arp', '-n']).split('\n')
            for index in range(1, len(arpData) - 1):
                iface = [data for data in arpData[index].replace(' ', ',').split(',') if data != '']
                if len(iface) > 2 and iface[2] == managementMac:
                    return iface[0]
            sleep(2)
        return None

    def ssh(self, user, passwd, managementIp):
        return call(['sshpass', '-p', str(passwd), 'ssh', '-o', 'StrictHostKeyChecking=no', str(user) + '@' + managementIp])


DEFAULT_VM_NETWORK_RUNTIME = VMNetworkRuntime()
