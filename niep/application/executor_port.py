"""Typed application port for the legacy topology executor.

Only :class:`LegacyExecutorAdapter` knows the historical executor attribute
names.  The lifecycle service and command handlers use ``ExecutorTopologyPort``
operations and snapshots, which keeps the compatibility surface explicit and
testable without importing Docker, libvirt or Mininet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from niep.application.lifecycle import TopologyState


@dataclass(frozen=True)
class ExecutorSnapshot:
    attached: bool = False
    lifecycle_state: TopologyState | None = None
    status: int | None = None
    status_present: bool = False
    detail: str = ""
    cleanup_required: bool = False
    cleanup_errors: tuple[Any, ...] = ()
    journal_length: int = 0
    journal_incomplete: bool = False
    active_resources: bool = False
    vm_ids: tuple[str, ...] = ()
    container_ids: tuple[str, ...] = ()
    vnf_ids: tuple[str, ...] = ()
    sfc_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # A concrete status value carries presence information for typed
        # fakes; the legacy adapter sets this explicitly so STATUS=None is
        # still distinguishable from an absent STATUS attribute.
        if self.status is not None and not self.status_present:
            object.__setattr__(self, "status_present", True)


class ExecutorTopologyPort(Protocol):
    """Operations required by the topology application service."""

    def attach(self, executor: Any) -> None: ...

    def detach(self) -> None: ...

    def compatibility_executor(self) -> Any: ...

    def snapshot(self) -> ExecutorSnapshot: ...

    def topology_up(self) -> Any: ...

    def topology_down(self) -> Any: ...

    def rollback_failed_start(self) -> Any: ...

    def set_cleanup(self, errors: list[Any], *, required: bool, status: int, detail: str) -> None: ...

    def mark_cleanup_pending(self) -> None: ...

    def image_ids(self) -> tuple[tuple[str, str], ...]: ...

    def persistent_done(self, key: tuple[str, str, str]) -> bool: ...

    def mark_persistent_done(self, key: tuple[str, str, str]) -> None: ...

    def get_resource(self, resource: str, resource_id: str) -> Any: ...

    def mininet_pingall(self) -> Any: ...

    def mininet_node_command(self, node_id: str, command: list[str]) -> str: ...

    def with_mininet_console(self, console: Any) -> Any: ...


class LegacyExecutorAdapter:
    """Adapter containing all reads/writes to legacy executor fields."""

    def __init__(self, executor: Any = None) -> None:
        self._legacy = executor

    def attach(self, executor: Any) -> None:
        self._legacy = executor

    def detach(self) -> None:
        self._legacy = None

    def compatibility_executor(self) -> Any:
        """Return the raw object only for explicitly legacy callers."""
        return self._legacy

    def snapshot(self) -> ExecutorSnapshot:
        executor = self._legacy
        if executor is None:
            return ExecutorSnapshot()
        lifecycle = getattr(executor, "lifecycle_state", None)
        if lifecycle is not None:
            lifecycle = TopologyState(lifecycle)
        resources = (
            "VMS",
            "VNFS",
            "CONTAINERS",
            "HOSTS",
            "SWITCHES",
            "OVSSWITCHES",
            "CONTROLLERS",
        )
        active = any(bool(getattr(executor, name, {})) for name in resources)
        # Executer currently exposes both spellings while older integrations
        # generally expose only one.  Resolve that compatibility detail here,
        # rather than teaching the lifecycle service about it.
        journal = getattr(executor, "JOURNAL", None)
        if journal is None:
            journal = getattr(executor, "journal", None)
        configuration = getattr(executor, "CONFIGURATION", None)
        sfcs = getattr(configuration, "SFCS", ()) if configuration is not None else ()
        if journal is None:
            journal_incomplete = False
        else:
            journal_incomplete = getattr(journal, "incomplete", None)
            if journal_incomplete is None:
                # Older doubles expose only a list/collection.  It cannot
                # distinguish compensated entries, so non-empty means that
                # reconciliation is still required for that legacy shape.
                journal_incomplete = bool(len(journal))
            elif callable(journal_incomplete):
                journal_incomplete = journal_incomplete()
        status_present = hasattr(executor, "STATUS")
        return ExecutorSnapshot(
            attached=True,
            lifecycle_state=lifecycle,
            status=getattr(executor, "STATUS", None),
            status_present=status_present,
            detail=getattr(executor, "DETAIL", "") or "",
            cleanup_required=bool(getattr(executor, "CLEANUP_REQUIRED", False)),
            cleanup_errors=tuple(getattr(executor, "CLEANUP_ERRORS", ()) or ()),
            journal_length=len(journal) if journal is not None else 0,
            journal_incomplete=bool(journal_incomplete),
            active_resources=active,
            vm_ids=tuple(getattr(executor, "VMS", {}).keys()),
            container_ids=tuple(getattr(executor, "CONTAINERS", {}).keys()),
            vnf_ids=tuple(getattr(executor, "VNFS", {}).keys()),
            sfc_ids=tuple(getattr(item, "ID", item) for item in sfcs),
        )

    def topology_up(self) -> Any:
        return self._legacy.topologyUp()

    def topology_down(self) -> Any:
        return self._legacy.topologyDown()

    def rollback_failed_start(self) -> Any:
        return self._legacy.rollbackFailedStart()

    def set_cleanup(self, errors: list[Any], *, required: bool, status: int, detail: str) -> None:
        self._legacy.CLEANUP_ERRORS = errors
        self._legacy.CLEANUP_REQUIRED = required
        self._legacy.STATUS = status
        self._legacy.DETAIL = detail

    def mark_cleanup_pending(self) -> None:
        transition = getattr(self._legacy, "_lifecycle_transition", None)
        if transition is not None:
            transition(TopologyState.CLEANUP_PENDING)

    def image_ids(self) -> tuple[tuple[str, str], ...]:
        return tuple(
            [("vnf_image", str(item.ID)) for item in self._legacy.VNFS.values()]
            + [("vm_image", str(item.ID)) for item in self._legacy.VMS.values()]
        )

    def _persistent_completed(self) -> set[tuple[str, str, str]]:
        completed = getattr(self._legacy, "_PERSISTENT_STATE_COMPLETED", None)
        if completed is None:
            completed = set()
            self._legacy._PERSISTENT_STATE_COMPLETED = completed
        return completed

    def persistent_done(self, key: tuple[str, str, str]) -> bool:
        return key in self._persistent_completed()

    def mark_persistent_done(self, key: tuple[str, str, str]) -> None:
        self._persistent_completed().add(key)

    def get_resource(self, resource: str, resource_id: str) -> Any:
        if resource == "vm":
            return self._legacy.VMS.get(resource_id)
        if resource == "container":
            return self._legacy.CONTAINERS.get(resource_id)
        if resource == "vnf":
            return self._legacy.VNFS.get(resource_id)
        if resource == "sfc":
            configuration = self._legacy.CONFIGURATION
            for item in configuration.SFCS:
                if item.ID == resource_id:
                    return item
            return None
        raise ValueError("unknown topology resource: " + resource)

    def mininet_pingall(self) -> Any:
        return self._legacy.NET.pingAll()

    def mininet_node_command(self, node_id: str, command: list[str]) -> str:
        return self._legacy.NET.get(node_id).cmd(" ".join(command))

    def with_mininet_console(self, console: Any) -> Any:
        return console(self._legacy.NET)


__all__ = ["ExecutorSnapshot", "ExecutorTopologyPort", "LegacyExecutorAdapter"]
