from signal import signal, SIGINT, SIG_IGN
from subprocess import CalledProcessError, Popen, check_output
from subprocess import DEVNULL, STDOUT
from sys import executable
from niep.paths import asset_path
from niep.runtime.errors import RuntimeFailure, cleanup_failure_record, command_failure
from niep.runtime.contracts import CommandRunner, ProcessRuntime
from niep.runtime.process import SubprocessRuntime


FNULL = DEVNULL


def pre_exec():
    signal(SIGINT, SIG_IGN)


def check_output_text(cmd, runner=None):
    data = (runner or SubprocessRuntime()).check_output(cmd)
    if isinstance(data, bytes):
        return data.decode("utf-8", "ignore")
    return data


class InfrastructureRuntime:
    """Global host-network and process adapter.

    ``prepare`` and ``cleanup`` are the canonical infrastructure contract;
    legacy topology method names remain as aliases.  Cleanup of an absent
    bridge/network is successful and repeated cleanup is idempotent.
    """

    def __init__(self, process_factory=None, command_runner=None, runner: CommandRunner | None = None, process_runtime: ProcessRuntime | None = None):
        # Keep the two infrastructure resources independent.  A bridge can be
        # removed even when libvirt reports an error (and vice versa), and a
        # retry must only revisit the operation that did not complete.
        self._CLEANUP_COMPLETED = set()
        self.CLEANUP_ERRORS = []
        # ``runner`` owns command execution (including sleep), whereas
        # ``process_runtime`` owns process handles.  They deliberately remain
        # independent: a process fake is not required to implement
        # ``check_output``/``call`` and must never be used as a command runner.
        self._runner = runner or SubprocessRuntime()
        self._process_runtime = process_runtime
        self._process_factory = process_factory or (process_runtime.start if process_runtime is not None else Popen)
        if command_runner is None:
            self._command_runner = self._runner.call
        elif callable(command_runner):
            self._command_runner = command_runner
        else:
            self._command_runner = command_runner.call

    def _check_output(self, command, *, operation="inspect", resource_type="host", resource_id=None):
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
                message="command failed while inspecting runtime state",
            ) from exc

    def _call(self, command, *, operation, resource_type, resource_id=None, **kwargs):
        try:
            return self._command_runner(command, **kwargs)
        except RuntimeFailure:
            raise
        except (CalledProcessError, OSError) as exc:
            raise command_failure(
                operation,
                resource_type,
                resource_id,
                command,
                exc,
                message="command failed while changing runtime state",
            ) from exc

    def interfaces_mapping(self):
        ifacesDictionary = {}

        ifacesData = self._check_output(
            ['brctl', 'show'], resource_type="host_network"
        ).split('\n')
        for iface in ifacesData[1:-1]:
            iface = iface.split('\t')
            if len(iface) > 5:
                ifacesDictionary[iface[0]] = iface[5]

        linkData = self._check_output(
            ['ip', '-o', 'link', 'show'], resource_type="host_network"
        ).split('\n')
        for link in linkData:
            linkColumns = link.split(': ')
            if len(linkColumns) >= 2:
                linkName = linkColumns[1].split('@')[0]
                ifacesDictionary.setdefault(linkName, linkName)

        return ifacesDictionary

    def bridge_exists(self, bridgeID):
        ifacesData = self._check_output(
            ['brctl', 'show'], resource_type="bridge", resource_id=bridgeID
        ).split('\n')
        for iface in ifacesData:
            if iface.startswith(bridgeID):
                return True
        return False

    def ensure_bridge(self, bridgeID):
        if not self.bridge_exists(bridgeID):
            status = self._call(
                ['brctl', 'addbr', bridgeID], operation="create",
                resource_type="bridge", resource_id=bridgeID,
                stdout=FNULL, stderr=STDOUT,
            )
            if status != 0:
                raise RuntimeFailure("prepare", "bridge", bridgeID, message="brctl addbr failed", context={"status": status})

    def ensure_virt_network(self, networkID, configPath):
        netData = self._check_output(
            ['virsh', 'net-list'], resource_type="libvirt_network", resource_id=networkID
        ).split('\n')
        for net in netData:
            netColumns = net.split()
            if netColumns and netColumns[0] == networkID:
                if len(netColumns) < 2 or netColumns[1] != 'active':
                    status = self._call(
                        ['virsh', 'net-start', networkID], operation="start",
                        resource_type="libvirt_network", resource_id=networkID,
                        stdout=FNULL, stderr=STDOUT,
                    )
                    if status != 0:
                        raise RuntimeFailure("prepare", "libvirt_network", networkID, message="virsh net-start failed", context={"status": status})
                return
        status = self._call(
            ['virsh', 'net-create', configPath], operation="create",
            resource_type="libvirt_network", resource_id=networkID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            raise RuntimeFailure("prepare", "libvirt_network", networkID, message="virsh net-create failed", context={"status": status})

    def start_local_pox(self):
        # POX remains an external controller tree and is deliberately not a
        # Python package dependency.  Resolve it from the source checkout only
        # when the Mininet integration path explicitly starts it.
        poxPath = str(asset_path('OFCONTROLLERS', 'pox', 'pox.py', description='OFCONTROLLERS/pox/pox.py'))
        process = self.start([executable, poxPath, 'forwarding.l2_learning'], stdout=FNULL, stderr=STDOUT, preexec_fn=pre_exec)
        self._runner.sleep(3)
        return process

    def start(self, command, **kwargs):
        try:
            if self._process_runtime is not None:
                return self._process_runtime.start(command, **kwargs)
            return self._process_factory(command, **kwargs)
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise RuntimeFailure("start", "process", None, cause=exc, retryable=True) from exc

    def terminate(self, process):
        try:
            if process is None:
                return None
            if hasattr(process, 'poll') and process.poll() is not None:
                return None
            if self._process_runtime is not None:
                return self._process_runtime.terminate(process)
            return process.terminate()
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise RuntimeFailure("terminate", "process", getattr(process, 'pid', None), cause=exc, retryable=True) from exc

    def wait(self, process, timeout=None):
        if process is None:
            return None
        try:
            if self._process_runtime is not None:
                return self._process_runtime.wait(process, timeout=timeout)
            return process.wait(timeout=timeout)
        except RuntimeFailure:
            raise
        except Exception as exc:
            raise RuntimeFailure("wait", "process", getattr(process, 'pid', None), cause=exc, retryable=True) from exc

    def stop_process(self, process):
        return self.terminate(process)

    def destroy_virt_network(self, networkID):
        activeNetworks = self._check_output(
            ['virsh', 'net-list', '--name'], operation="inspect",
            resource_type="libvirt_network", resource_id=networkID,
        ).splitlines()
        if networkID not in activeNetworks:
            return
        status = self._call(
            ['virsh', 'net-destroy', networkID], operation="destroy",
            resource_type="libvirt_network", resource_id=networkID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            raise RuntimeFailure(
                "cleanup", "libvirt_network", networkID,
                message="virsh net-destroy failed",
                context={"status": status},
            )

    def remove_bridge(self, bridgeID):
        if not self.bridge_exists(bridgeID):
            return
        errors = []
        status = self._call(
            ['ifconfig', bridgeID, 'down'], operation="stop",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            errors.append("ifconfig down returned " + str(status))
        status = self._call(
            ['brctl', 'delbr', bridgeID], operation="remove",
            resource_type="bridge", resource_id=bridgeID,
            stdout=FNULL, stderr=STDOUT,
        )
        if status != 0:
            errors.append("brctl delbr returned " + str(status))
        if errors:
            raise RuntimeFailure("cleanup", "bridge", bridgeID, message=" | ".join(errors))

    def prepare_topology_infrastructure(self):
        self._CLEANUP_COMPLETED = set()
        self.CLEANUP_ERRORS = []
        self.ensure_bridge('vbrNIEP')
        configPath = str(asset_path('CONFS', 'vnNIEP.xml', description='CONFS/vnNIEP.xml'))
        self.ensure_virt_network('vnNIEP', configPath)

    def prepare(self):
        return self.prepare_topology_infrastructure()

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
            except RuntimeFailure as exc:
                record = cleanup_failure_record(
                    exc,
                    resource_type="libvirt_network",
                    resource_id="vnNIEP",
                    operation="destroy",
                )
                # Keep the historical nested field for callers that consumed
                # it, while exposing the complete safe record at the boundary.
                record["failure"] = dict(record)
                cleanupErrors.append(record)
            except Exception as exc:
                cleanupErrors.append(cleanup_failure_record(
                    exc,
                    resource_type="libvirt_network",
                    resource_id="vnNIEP",
                    operation="destroy",
                ))
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
            except RuntimeFailure as exc:
                record = cleanup_failure_record(
                    exc,
                    resource_type="bridge",
                    resource_id="vbrNIEP",
                    operation="remove",
                )
                record["failure"] = dict(record)
                cleanupErrors.append(record)
            except Exception as exc:
                cleanupErrors.append(cleanup_failure_record(
                    exc,
                    resource_type="bridge",
                    resource_id="vbrNIEP",
                    operation="remove",
                ))
            else:
                completed.add(bridgeKey)

        self.CLEANUP_ERRORS = cleanupErrors
        return -10 if cleanupErrors else 0

    def cleanup(self):
        return self.cleanup_topology_infrastructure()


DEFAULT_INFRASTRUCTURE_RUNTIME = InfrastructureRuntime()
