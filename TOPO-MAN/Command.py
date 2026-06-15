from Result import ResultCode, ServiceResult
from Service import TopologyService, VMService, VNFService, SFCService


class CommandDispatcher:
    def __init__(self, topology=None):
        self.topology = topology or TopologyService()
        self.vm = VMService(self.topology)
        self.vnf = VNFService(self.topology)
        self.sfc = SFCService(self.topology)

    def dispatch(self, command, args=None):
        args = args or []
        try:
            return self._dispatch(command, args)
        except Exception as exc:
            return ServiceResult(
                ok=False,
                code=ResultCode.COMMAND_ERROR,
                message=str(exc),
            )

    def _dispatch(self, command, args):
        if command == 'define':
            return self._expect_args(args, 1, lambda: self._hide_internal_data(self.topology.define(args[0])))
        if command == 'topoup':
            return self._expect_args(args, 0, lambda: self._hide_internal_data(self.topology.up()))
        if command == 'topodown':
            return self._expect_args(args, 0, self.topology.down)
        if command == 'topoclean':
            return self._expect_args(args, 0, self.topology.clean)
        if command == 'topodestroy':
            return self._expect_args(args, 0, self.topology.destroy)
        if command == 'status':
            return self._expect_args(args, 0, self.status)
        if command == 'vm':
            return self.vm_command(args)
        if command == 'vnf':
            return self.vnf_command(args)
        if command == 'sfc':
            return self.sfc_command(args)
        if command == 'mininet':
            return self.mininet_command(args)

        return ServiceResult(
            ok=False,
            code=ResultCode.UNKNOWN_COMMAND,
            message="UNKNOWN COMMAND",
        )

    def status(self):
        data = {
            'defined': self.topology.executor is not None,
            'up': self.topology.is_up(),
            'vms': self.topology.vm_ids(),
            'vnfs': self.topology.vnf_ids(),
            'sfcs': self.topology.sfc_ids(),
        }
        return ServiceResult(ok=True, code=ResultCode.STATUS, data=data)

    def vm_command(self, args):
        if not args:
            return self._invalid_args("VM COMMAND EXPECTED")
        if args[0] == 'list':
            return self._expect_args(args, 1, lambda: ServiceResult(ok=True, code=ResultCode.DEFINED, data=self.topology.vm_ids()))
        if args[0] == 'management':
            return self._expect_args(args, 2, lambda: self.vm.management(args[1]))
        if args[0] == 'ssh':
            return self._expect_args(args, 4, lambda: self.vm.ssh(args[1], args[2], args[3]))
        return self._unknown_subcommand('VM')

    def vnf_command(self, args):
        if not args:
            return self._invalid_args("VNF COMMAND EXPECTED")
        if args[0] == 'list':
            return self._expect_args(args, 1, lambda: ServiceResult(ok=True, code=ResultCode.DEFINED, data=self.topology.vnf_ids()))
        if args[0] == 'management':
            return self._expect_args(args, 2, lambda: self.vnf.management(args[1]))
        if args[0] == 'up':
            return self._expect_args(args, 2, lambda: self.vnf.up(args[1]))
        if args[0] == 'down':
            return self._expect_args(args, 2, lambda: self.vnf.down(args[1]))
        if args[0] == 'action':
            if len(args) < 3:
                return self._invalid_args("VNF ACTION EXPECTS VNF ID AND ACTION")
            return self.vnf.action(args[1], args[2], args[3:])
        if args[0] == 'script':
            if len(args) not in (3, 4):
                return self._invalid_args("VNF SCRIPT EXPECTS VNF ID, SCRIPT AND OPTIONAL ERROR SCRIPT")
            error_script = args[3] if len(args) == 4 else None
            return self.vnf.script(args[1], args[2], error_script)
        return self._unknown_subcommand('VNF')

    def sfc_command(self, args):
        if not args:
            return self._invalid_args("SFC COMMAND EXPECTED")
        if args[0] == 'list':
            return self._expect_args(args, 1, lambda: ServiceResult(ok=True, code=ResultCode.DEFINED, data=self.topology.sfc_ids()))
        if args[0] == 'management':
            return self._expect_args(args, 2, lambda: self.sfc.management(args[1]))
        if args[0] == 'up':
            return self._expect_args(args, 2, lambda: self.sfc.up(args[1]))
        if args[0] == 'down':
            return self._expect_args(args, 2, lambda: self.sfc.down(args[1]))
        return self._unknown_subcommand('SFC')

    def mininet_command(self, args):
        if not self.topology.is_up():
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_NOT_UP,
                message="TOPOLOGY IS NOT UP",
            )
        if not args:
            return self._invalid_args("MININET COMMAND EXPECTED")
        if args[0] == 'pingall':
            return self._expect_args(args, 1, self.mininet_pingall)
        if args[0] == 'cmd':
            if len(args) < 3:
                return self._invalid_args("MININET CMD EXPECTS NODE AND COMMAND")
            return self.mininet_node_command(args[1], args[2:])
        return self._unknown_subcommand('MININET')

    def mininet_pingall(self):
        dropped = self.topology.executor.NET.pingAll()
        return ServiceResult(
            ok=True,
            code=ResultCode.MININET_RESULT,
            data={'dropped': dropped},
        )

    def mininet_node_command(self, node_id, command):
        try:
            node = self.topology.executor.NET.get(node_id)
        except KeyError:
            return ServiceResult(
                ok=False,
                code=ResultCode.NODE_NOT_FOUND,
                message="NODE NOT FOUND",
            )
        output = node.cmd(' '.join(command))
        return ServiceResult(
            ok=True,
            code=ResultCode.NODE_COMMAND,
            data={'node': node_id, 'output': output},
        )

    def _expect_args(self, args, amount, callback):
        if len(args) != amount:
            return self._invalid_args("WRONG ARGUMENTS AMOUNT - " + str(amount) + " EXPECTED")
        return callback()

    def _invalid_args(self, message):
        return ServiceResult(
            ok=False,
            code=ResultCode.INVALID_COMMAND_ARGS,
            message=message,
        )

    def _unknown_subcommand(self, subject):
        return ServiceResult(
            ok=False,
            code=ResultCode.UNKNOWN_COMMAND,
            message="UNKNOWN " + subject + " COMMAND",
        )

    def _hide_internal_data(self, result):
        if not result.ok:
            return result
        return ServiceResult(
            ok=True,
            code=result.code,
            message=result.message,
            status=result.status,
            detail=result.detail,
        )
