from subprocess import CalledProcessError, DEVNULL, PIPE, STDOUT

from niep.runtime.errors import RuntimeFailure
from niep.runtime.contracts import CommandRunner
from niep.runtime.process import SubprocessRuntime

FNULL = DEVNULL


class ContainerNetworkError(RuntimeFailure):
    def __init__(self, operation, interface_id, command, output, *, cause=None, retryable=False):
        self.interface_id = interface_id
        self.command = command
        self.output = output
        text = output.decode("utf-8", "replace") if isinstance(output, bytes) else str(output or "")
        detail = "Container network operation failed: " + str(operation)
        if text.strip():
            detail += "; output=" + text.strip()
        super().__init__(
            operation,
            "interface",
            interface_id,
            cause=cause,
            retryable=retryable,
            context={"command": list(command), "output": text},
            message=detail,
        )


def check_output_text(cmd, runner=None):
    data = (runner or SubprocessRuntime()).check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class ContainerNetworkRuntime:
    def __init__(self, runner: CommandRunner | None = None, process_runtime: CommandRunner | None = None):
        self._runner = runner or process_runtime or SubprocessRuntime()

    def _command_failure(self, operation, interface_id, command, exc):
        output = getattr(exc, "output", None) or str(exc)
        return ContainerNetworkError(
            operation,
            interface_id,
            command,
            output,
            cause=exc,
            retryable=not isinstance(exc, CalledProcessError),
        )

    def run_checked(self, operation, interface_id, command):
        try:
            completed = self._runner.run(command, stdout=PIPE, stderr=STDOUT, text=True)
        except RuntimeFailure:
            raise
        except (CalledProcessError, OSError) as exc:
            raise self._command_failure(operation, interface_id, command, exc) from exc
        if completed.returncode != 0:
            raise ContainerNetworkError(operation, interface_id, command, completed.stdout, retryable=False)
        return completed.stdout

    def interface_exists(self, interface_id):
        try:
            return self._runner.call(['ip', 'link', 'show', interface_id], stdout=FNULL, stderr=STDOUT) == 0
        except RuntimeFailure:
            raise
        except (CalledProcessError, OSError) as exc:
            command = ['ip', 'link', 'show', interface_id]
            raise self._command_failure("inspect", interface_id, command, exc) from exc

    def delete_interface(self, interface_id):
        if self.interface_exists(interface_id):
            self.run_checked("delete", interface_id, ['ip', 'link', 'del', interface_id])

    def prepare(self, container, interfaces=None):
        """Prepare and attach container interfaces (the canonical seam)."""

        return self.setup_interfaces(container, interfaces or [])

    def attach(self, container, interfaces=None):
        return self.setup_interfaces(container, interfaces or [])

    def detach(self, interfaces):
        return self.release_interfaces(interfaces or [])

    def cleanup(self, interfaces):
        # Missing interfaces are successful cleanup by contract.
        return self.release_interfaces(interfaces or [])

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
