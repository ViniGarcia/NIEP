"""Application-owned active topology session.

Interfaces receive command responses and stream handles; they never need to
know which executor or runtime adapter currently backs this session.
"""

from __future__ import annotations

from typing import Any, Callable

from niep.application.service import TopologyService


class TopologySession:
    """Single application owner for the active :class:`TopologyService`."""

    # ``LegacyExecutorAdapter`` is the only boundary that reads legacy runtime
    # fields. Command handlers and interfaces consume the typed operations and
    # snapshots below instead of reaching into an executor.

    def __init__(self, topology: TopologyService | None = None) -> None:
        self._topology = topology or TopologyService()

    def define(self, definition_path: str) -> Any:
        return self._topology.define(definition_path)

    def up(self) -> Any:
        return self._topology.up()

    def down(self) -> Any:
        return self._topology.down()

    def clean(self) -> Any:
        return self._topology.clean()

    def destroy(self) -> Any:
        return self._topology.destroy()

    @property
    def state(self) -> Any:
        return self._topology.state

    @property
    def is_defined(self) -> bool:
        return self._topology.is_defined()

    def is_up(self) -> bool:
        return self._topology.is_up()

    def resource_ids(self, resource: str) -> list[str]:
        readers = {
            "vms": self._topology.vm_ids,
            "containers": self._topology.container_ids,
            "vnfs": self._topology.vnf_ids,
            "sfcs": self._topology.sfc_ids,
        }
        try:
            return list(readers[resource]())
        except KeyError as exc:
            raise ValueError("unknown topology resource: " + resource) from exc

    def status(self) -> dict[str, Any]:
        return {
            "defined": self.is_defined,
            "up": self.is_up(),
            "vms": self.resource_ids("vms"),
            "containers": self.resource_ids("containers"),
            "vnfs": self.resource_ids("vnfs"),
            "sfcs": self.resource_ids("sfcs"),
        }

    def service_for(self, resource: str) -> Any:
        """Create an application service bound to this session.

        This is intentionally a narrow application seam.  It is not exposed
        by any command DTO and is used only by aggregate handlers.
        """

        from niep.application.service import (
            ContainerService,
            SFCService,
            VMService,
            VNFService,
        )

        services = {
            "vm": VMService,
            "container": ContainerService,
            "vnf": VNFService,
            "sfc": SFCService,
        }
        try:
            return services[resource](self._topology)
        except KeyError as exc:
            raise ValueError("unknown topology service: " + resource) from exc

    def mininet_pingall(self) -> Any:
        return self._topology.mininet_pingall()

    def mininet_node_command(self, node_id: str, command: list[str]) -> str:
        try:
            return self._topology.mininet_node_command(node_id, command)
        except KeyError:
            raise

    def with_mininet_console(self, console: Callable[[Any], Any]) -> Any:
        """Run a legacy Mininet console inside the application boundary."""

        return self._topology.with_mininet_console(console)

    def get_resource(self, resource: str, resource_id: str) -> Any:
        readers = {
            "vm": self._topology.get_vm,
            "container": self._topology.get_container,
            "vnf": self._topology.get_vnf,
            "sfc": self._topology.get_sfc,
        }
        try:
            return readers[resource](resource_id)
        except KeyError as exc:
            raise ValueError("unknown topology resource: " + resource) from exc


__all__ = ["TopologySession"]
