from subprocess import CalledProcessError, DEVNULL, STDOUT

from niep.runtime.errors import RuntimeFailure, command_failure
from niep.runtime.contracts import CommandRunner
from niep.runtime.process import SubprocessRuntime

FNULL = DEVNULL


def check_output_text(cmd, runner=None):
    data = (runner or SubprocessRuntime()).check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class VMNetworkRuntime:
    def __init__(self, runner: CommandRunner | None = None, process_runtime: CommandRunner | None = None):
        self._runner = runner or process_runtime or SubprocessRuntime()

    def _check_output(self, command, *, operation="inspect", resource_type="network", resource_id=None):
        try:
            return check_output_text(command, self._runner)
        except RuntimeFailure:
            raise
        except (CalledProcessError, OSError) as exc:
            raise command_failure(
                operation,
                resource_type,
                resource_id,
                command,
                exc,
                message="command failed while inspecting network state",
            ) from exc

    def _call(self, command, *, operation, resource_type, resource_id=None, **kwargs):
        try:
            return self._runner.call(command, **kwargs)
        except RuntimeFailure:
            raise
        except (CalledProcessError, OSError) as exc:
            raise command_failure(
                operation,
                resource_type,
                resource_id,
                command,
                exc,
                message="command failed while changing network state",
            ) from exc

    def bridge_lines(self):
        return self._check_output(
            ['brctl', 'show'], operation="inspect", resource_type="bridge"
        ).split('\n')

    def bridge_exists(self, bridgeID):
        for bridgeLine in self.bridge_lines():
            if bridgeLine.startswith(bridgeID):
                return True
        return False

    def create_bridge(self, bridgeID, mac):
        status = self._call(
            ['brctl', 'addbr', bridgeID], operation="create",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            raise RuntimeFailure("create", "bridge", bridgeID, message="brctl addbr failed", context={"status": status})
        status = self._call(
            ['ifconfig', bridgeID, "hw", "ether", mac], operation="configure",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            raise RuntimeFailure("configure", "bridge", bridgeID, message="ifconfig hw ether failed", context={"status": status})

    def enable_bridge(self, bridgeID):
        status = self._call(
            ['ifconfig', bridgeID, 'up'], operation="start",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            raise RuntimeFailure("start", "bridge", bridgeID, message="ifconfig up failed", context={"status": status})

    def disable_bridge(self, bridgeID):
        return self._call(
            ['ifconfig', bridgeID, 'down'], operation="stop",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )

    def delete_bridge(self, bridgeID):
        return self._call(
            ['brctl', 'delbr', bridgeID], operation="remove",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )

    def prepare(self, interfaces):
        return self.prepare_interfaces(interfaces or [])

    def attach(self, interfaces):
        return self.prepare_interfaces(interfaces or [])

    def detach(self, interfaces):
        return self.release_interfaces(interfaces or [])

    def cleanup(self, interfaces):
        # A bridge that is already absent is a successful, idempotent cleanup.
        return self.release_interfaces(interfaces or [])

    def prepare_interfaces(self, interfaces):
        for iface in interfaces:
            if not self.bridge_exists(iface['ID']):
                self.create_bridge(iface['ID'], iface['LINK_MAC'])
        for iface in interfaces:
            self.enable_bridge(iface['ID'])

    def release_interfaces(self, interfaces):
        errors = []
        for iface in interfaces:
            interfaceID = iface['ID']
            if not self.bridge_exists(interfaceID):
                continue
            downStatus = self.disable_bridge(interfaceID)
            if downStatus != 0:
                errors.append(
                    "ifconfig down failed for " + str(interfaceID) + " with status " + str(downStatus)
                )
            deleteStatus = self.delete_bridge(interfaceID)
            if deleteStatus != 0:
                errors.append(
                    "brctl delbr failed for " + str(interfaceID) + " with status " + str(deleteStatus)
                )
        if errors:
            raise RuntimeFailure(
                "cleanup",
                "bridge",
                ",".join(str(item.get("ID", "unknown")) for item in interfaces),
                message=" | ".join(errors),
            )

    def management_ip(self, managementMac):
        for attempt in range(0, 3):
            arpData = self._check_output(
                ['arp', '-n'], operation="inspect", resource_type="management_network",
                resource_id=managementMac,
            ).split('\n')
            for index in range(1, len(arpData) - 1):
                iface = [data for data in arpData[index].replace(' ', ',').split(',') if data != '']
                if len(iface) > 2 and iface[2] == managementMac:
                    return iface[0]
            self._runner.sleep(2)
        return None

    def ssh(self, user, passwd, managementIp):
        return self._call(
            ['sshpass', '-p', str(passwd), 'ssh', '-o', 'StrictHostKeyChecking=no', str(user) + '@' + managementIp],
            operation="ssh", resource_type="vm", resource_id=managementIp,
        )


DEFAULT_VM_NETWORK_RUNTIME = VMNetworkRuntime()
