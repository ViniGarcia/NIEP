"""Small aggregate command handlers.

Handlers translate validated command arguments into existing application
services.  They return ``ServiceResult`` for the legacy facade; the router is
responsible for converting those results into the versioned public DTO.
"""

from __future__ import annotations

from collections.abc import Callable
from niep.application.session import TopologySession
from niep.domain.result import ResultCode, ServiceResult


class Handler:
    def __init__(self, session: TopologySession) -> None:
        self.session = session

    @staticmethod
    def exact(args: tuple[str, ...], amount: int, callback: Callable[[], ServiceResult]) -> ServiceResult:
        if len(args) != amount:
            return ServiceResult(
                ok=False,
                code=ResultCode.INVALID_COMMAND_ARGS,
                message="WRONG ARGUMENTS AMOUNT - " + str(amount) + " EXPECTED",
            )
        return callback()

    @staticmethod
    def invalid(message: str) -> ServiceResult:
        return ServiceResult(ok=False, code=ResultCode.INVALID_COMMAND_ARGS, message=message)

    @staticmethod
    def unknown(subject: str) -> ServiceResult:
        return ServiceResult(
            ok=False,
            code=ResultCode.UNKNOWN_COMMAND,
            message="UNKNOWN " + subject + " COMMAND",
        )


class TopologyCommandHandler(Handler):
    def define(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(args, 1, lambda: self.session.define(args[0]))

    def up(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(args, 0, self.session.up)

    def down(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(args, 0, self.session.down)

    def clean(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(args, 0, self.session.clean)

    def destroy(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(args, 0, self.session.destroy)

    def status(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(
            args,
            0,
            lambda: ServiceResult(ok=True, code=ResultCode.STATUS, data=self.session.status()),
        )


class VMCommandHandler(Handler):
    def __init__(self, session: TopologySession) -> None:
        super().__init__(session)
        self.service = session.service_for("vm")

    def handle(self, args: tuple[str, ...]) -> ServiceResult:
        if not args:
            return self.invalid("VM COMMAND EXPECTED")
        if args[0] == "list":
            return self.exact(
                args,
                1,
                lambda: ServiceResult(
                    ok=True, code=ResultCode.DEFINED, data=self.session.resource_ids("vms")
                ),
            )
        if args[0] == "management":
            return self.exact(args, 2, lambda: self.service.management(args[1]))
        if args[0] == "ssh":
            return self.exact(args, 4, lambda: self.service.ssh(args[1], args[2], args[3]))
        return self.unknown("VM")


class ContainerCommandHandler(Handler):
    def __init__(self, session: TopologySession) -> None:
        super().__init__(session)
        self.service = session.service_for("container")

    def handle(self, args: tuple[str, ...]) -> ServiceResult:
        if not args:
            return self.invalid("CONTAINER COMMAND EXPECTED")
        if args[0] == "list":
            return self.exact(
                args,
                1,
                lambda: ServiceResult(
                    ok=True,
                    code=ResultCode.DEFINED,
                    data=self.session.resource_ids("containers"),
                ),
            )
        if args[0] == "exec":
            if len(args) < 3:
                return self.invalid("CONTAINER EXEC EXPECTS CONTAINER ID AND COMMAND")
            return self.service.exec(args[1], list(args[2:]))
        if args[0] == "shell":
            return self.invalid("CONTAINER SHELL REQUIRES AN INTERACTIVE CLIENT")
        return self.unknown("CONTAINER")

    def open_stream(self, args: tuple[str, ...]) -> ServiceResult:
        if len(args) < 2 or args[0] != "shell":
            return self.invalid("CONTAINER SHELL REQUIRES AN INTERACTIVE CLIENT")
        command = list(args[2:]) or ["/bin/sh"]
        return self.service.open_shell(args[1], command)


class VNFCommandHandler(Handler):
    def __init__(self, session: TopologySession) -> None:
        super().__init__(session)
        self.service = session.service_for("vnf")

    def handle(self, args: tuple[str, ...]) -> ServiceResult:
        if not args:
            return self.invalid("VNF COMMAND EXPECTED")
        if args[0] == "list":
            return self.exact(
                args,
                1,
                lambda: ServiceResult(
                    ok=True, code=ResultCode.DEFINED, data=self.session.resource_ids("vnfs")
                ),
            )
        if args[0] == "management":
            return self.exact(args, 2, lambda: self.service.management(args[1]))
        if args[0] == "up":
            return self.exact(args, 2, lambda: self.service.up(args[1]))
        if args[0] == "down":
            return self.exact(args, 2, lambda: self.service.down(args[1]))
        if args[0] == "action":
            if len(args) < 3:
                return self.invalid("VNF ACTION EXPECTS VNF ID AND ACTION")
            return self.service.action(args[1], args[2], list(args[3:]))
        if args[0] == "script":
            if len(args) not in (3, 4):
                return self.invalid(
                    "VNF SCRIPT EXPECTS VNF ID, SCRIPT AND OPTIONAL ERROR SCRIPT"
                )
            return self.service.script(args[1], args[2], args[3] if len(args) == 4 else None)
        return self.unknown("VNF")

    def actions(self, args: tuple[str, ...]) -> ServiceResult:
        return self.exact(args, 1, lambda: self.service.actions(args[0]))


class SFCCommandHandler(Handler):
    def __init__(self, session: TopologySession) -> None:
        super().__init__(session)
        self.service = session.service_for("sfc")

    def handle(self, args: tuple[str, ...]) -> ServiceResult:
        if not args:
            return self.invalid("SFC COMMAND EXPECTED")
        if args[0] == "list":
            return self.exact(
                args,
                1,
                lambda: ServiceResult(
                    ok=True, code=ResultCode.DEFINED, data=self.session.resource_ids("sfcs")
                ),
            )
        if args[0] == "management":
            return self.exact(args, 2, lambda: self.service.management(args[1]))
        if args[0] == "up":
            return self.exact(args, 2, lambda: self.service.up(args[1]))
        if args[0] == "down":
            return self.exact(args, 2, lambda: self.service.down(args[1]))
        return self.unknown("SFC")


class MininetCommandHandler(Handler):
    def handle(self, args: tuple[str, ...]) -> ServiceResult:
        if not self.session.is_up():
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_NOT_UP,
                message="TOPOLOGY IS NOT UP",
            )
        if not args:
            return self.invalid("MININET COMMAND EXPECTED")
        if args[0] == "pingall":
            return self.exact(args, 1, self.pingall)
        if args[0] == "cmd":
            if len(args) < 3:
                return self.invalid("MININET CMD EXPECTS NODE AND COMMAND")
            return self.node_command(args[1], list(args[2:]))
        return self.unknown("MININET")

    def pingall(self) -> ServiceResult:
        return ServiceResult(
            ok=True,
            code=ResultCode.MININET_RESULT,
            data={"dropped": self.session.mininet_pingall()},
        )

    def node_command(self, node_id: str, command: list[str]) -> ServiceResult:
        try:
            output = self.session.mininet_node_command(node_id, command)
        except KeyError:
            return ServiceResult(ok=False, code=ResultCode.NODE_NOT_FOUND, message="NODE NOT FOUND")
        return ServiceResult(
            ok=True,
            code=ResultCode.NODE_COMMAND,
            data={"node": node_id, "output": output},
        )


__all__ = [
    "ContainerCommandHandler",
    "Handler",
    "MininetCommandHandler",
    "SFCCommandHandler",
    "TopologyCommandHandler",
    "VMCommandHandler",
    "VNFCommandHandler",
]
