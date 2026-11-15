"""Command use-cases and the legacy ``CommandDispatcher`` facade."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping
from typing import Any

from niep.application.commands import CommandProtocolError, CommandRequest, CommandResponse
from niep.application.handlers import (
    ContainerCommandHandler,
    MininetCommandHandler,
    SFCCommandHandler,
    TopologyCommandHandler,
    VMCommandHandler,
    VNFCommandHandler,
)
from niep.application.disk_usage import DiskUsageService
from niep.application.startup_timing import StartupTimingService
from niep.application.metrics import MetricsService
from niep.application.session import TopologySession
from niep.application.service import (
    ContainerService,
    SFCService,
    TopologyService,
    VMService,
    VNFService,
)
from niep.domain.result import ResultCode, ServiceResult


def _json_safe(value: Any) -> Any:
    """Normalize old service payloads before they cross an interface."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("non-finite command response data")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("command response object keys must be strings")
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    raise TypeError("unsupported command response data type")


def _public_result(result: ServiceResult) -> ServiceResult:
    """Apply the public command boundary to an existing service result."""

    code = result.code.value if hasattr(result.code, "value") else str(result.code)
    data = result.data
    # TopologyService retains these objects for its lifecycle compatibility
    # tests, but a command response must not leak parser/executor instances.
    if code in {
        ResultCode.TOPOLOGY_UP.value,
        ResultCode.PARSER_ERROR.value,
        ResultCode.EXECUTER_ERROR.value,
        ResultCode.CONTAINER_SHELL.value,
    }:
        data = None
    else:
        try:
            data = _json_safe(data)
        except TypeError:
            # ``defined`` is also the historical success code for aggregate
            # list commands. Preserve JSON lists while fail-closing the raw
            # parser/executor object returned by the lifecycle compatibility
            # service.
            if code == ResultCode.DEFINED.value:
                data = None
            else:
                return ServiceResult(
                    ok=False,
                    code=ResultCode.COMMAND_ERROR,
                    message="COMMAND RESPONSE CONTAINS UNSUPPORTED DATA",
                )
    return ServiceResult(
        ok=result.ok,
        code=result.code,
        message=result.message,
        data=data,
        status=result.status,
        detail=result.detail,
    )


class CommandRouter:
    """Registry-based command router."""

    def __init__(self, session: TopologySession) -> None:
        self.session = session
        topology = TopologyCommandHandler(session)
        self._topology = topology
        self._container = ContainerCommandHandler(session)
        self._vm = VMCommandHandler(session)
        self._vnf = VNFCommandHandler(session)
        self._sfc = SFCCommandHandler(session)
        self._mininet = MininetCommandHandler(session)
        self._startup_timing = StartupTimingService(session)
        self._metrics = MetricsService(session)
        self._disk_usage = DiskUsageService(session)
        self._routes: dict[str, Callable[[tuple[str, ...]], ServiceResult]] = {
            "define": topology.define,
            "topoup": lambda args: self._startup_timing.up(args, topology.up),
            "topodown": lambda args: self._startup_timing.stop(args, topology.down),
            "topoclean": lambda args: self._startup_timing.stop(args, topology.clean),
            "topodestroy": lambda args: self._startup_timing.stop(args, topology.destroy),
            "status": topology.status,
            "stats": self._metrics.snapshot,
            "startup-timing": self._startup_timing.handle,
            "disk-usage": self._disk_usage.snapshot,
            "vm": self._vm.handle,
            "container": self._container.handle,
            "vnf": self._vnf.handle,
            "sfc": self._sfc.handle,
            "mininet": self._mininet.handle,
        }

    @property
    def routes(self) -> tuple[str, ...]:
        return tuple(sorted(self._routes))

    def register(self, command: str, handler: Callable[[tuple[str, ...]], ServiceResult]) -> None:
        if not command or not isinstance(command, str):
            raise ValueError("command name must be a non-empty string")
        if command in self._routes:
            raise ValueError("command already registered: " + command)
        self._routes[command] = handler

    def dispatch(self, request: CommandRequest) -> ServiceResult:
        try:
            handler = self._routes[request.command]
        except KeyError:
            return ServiceResult(ok=False, code=ResultCode.UNKNOWN_COMMAND, message="UNKNOWN COMMAND")
        try:
            return handler(request.args)
        except Exception:
            return ServiceResult(
                ok=False,
                code=ResultCode.COMMAND_ERROR,
                message="COMMAND EXECUTION FAILED",
            )

    def open_container_stream(self, args: tuple[str, ...]) -> ServiceResult:
        """Open a shell for a socket/CLI stream adapter, out of band."""

        return self._container.open_stream(args)


class CommandDispatcher:
    """Compatibility facade for legacy callers and the v1 command port."""

    def __init__(self, topology: TopologyService | TopologySession | None = None) -> None:
        self.session = topology if isinstance(topology, TopologySession) else TopologySession(topology)
        # Compatibility attribute for existing lifecycle tests.  New
        # interfaces use ``session`` and never inspect its executor.
        self.topology = self.session._topology
        self.router = CommandRouter(self.session)
        self.vm = VMService(self.topology)
        self.container = ContainerService(self.topology)
        self.vnf = VNFService(self.topology)
        self.sfc = SFCService(self.topology)

    def request(self, command: str, args: list[str] | tuple[str, ...] | None = None) -> CommandRequest:
        return CommandRequest(command=command, args=tuple(args or ()))

    def dispatch_request(self, request: CommandRequest | Mapping[str, Any]) -> CommandResponse:
        try:
            if not isinstance(request, CommandRequest):
                request = CommandRequest.from_dict(request)
            result = _public_result(self.router.dispatch(request))
            try:
                return CommandResponse.from_result(request, result)
            except CommandProtocolError as exc:
                return CommandResponse.failure(request.request_id, exc.code, str(exc))
        except CommandProtocolError as exc:
            request_id = request.get("request_id", "") if isinstance(request, Mapping) else ""
            if not isinstance(request_id, str) or not request_id:
                request_id = "invalid"
            return CommandResponse.failure(request_id, exc.code, str(exc))

    def dispatch(self, command: str, args: list[str] | tuple[str, ...] | None = None) -> ServiceResult:
        try:
            request = self.request(command, args)
        except CommandProtocolError as exc:
            return ServiceResult(ok=False, code=ResultCode.COMMAND_ERROR, message=str(exc))
        return self.dispatch_request(request).to_service_result()

    def status(self) -> ServiceResult:
        return self.dispatch("status")

    def vm_command(self, args: list[str] | tuple[str, ...]) -> ServiceResult:
        return self.dispatch("vm", args)

    def container_command(self, args: list[str] | tuple[str, ...]) -> ServiceResult:
        return self.dispatch("container", args)

    def vnf_command(self, args: list[str] | tuple[str, ...]) -> ServiceResult:
        return self.dispatch("vnf", args)

    def vnf_actions(self, vnf_id: str) -> ServiceResult:
        return _public_result(self.router._vnf.actions((vnf_id,)))

    def sfc_command(self, args: list[str] | tuple[str, ...]) -> ServiceResult:
        return self.dispatch("sfc", args)

    def mininet_command(self, args: list[str] | tuple[str, ...]) -> ServiceResult:
        return self.dispatch("mininet", args)

    def mininet_pingall(self) -> ServiceResult:
        return self.dispatch("mininet", ("pingall",))

    def mininet_node_command(self, node_id: str, command: list[str]) -> ServiceResult:
        return self.dispatch("mininet", ("cmd", node_id, *command))

    def open_stream(self, command: str, args: list[str] | tuple[str, ...]) -> ServiceResult:
        if command != "container":
            return ServiceResult(
                ok=False,
                code=ResultCode.INVALID_COMMAND_ARGS,
                message="INTERACTIVE STREAM IS NOT SUPPORTED FOR " + command.upper(),
            )
        return self.router.open_container_stream(tuple(args))

    def open_mininet_console(self) -> Any:
        # Keep the optional Mininet import in the application boundary.  The
        # legacy interface only requests the use case and receives no NET
        # object.
        try:
            from mininet.cli import CLI
        except ImportError as exc:  # pragma: no cover - integration-only path
            raise RuntimeError("Mininet is unavailable; install the integration dependencies") from exc
        return self.session.with_mininet_console(CLI)

    @staticmethod
    def result_json(result: ServiceResult) -> str:
        return json.dumps(_public_result(result).to_dict(), sort_keys=True)


__all__ = [
    "CommandDispatcher",
    "CommandRouter",
    "CommandProtocolError",
    "CommandRequest",
    "CommandResponse",
]
