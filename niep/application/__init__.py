"""Application services and command dispatch.

Imports are lazy because creating an application service may load an optional
runtime adapter.  This keeps package discovery and metadata tools usable on a
host without Mininet/libvirt/Docker.
"""

__all__ = [
    "CommandDispatcher",
    "ContainerService",
    "SFCService",
    "TopologyService",
    "VMService",
    "VNFService",
    "PathResolver",
    "RuntimeFactory",
    "TopologyLoader",
    "TopologyValidator",
    "TopologyPlanner",
    "TopologyPlanningError",
    "PlanningError",
    "MininetTopologyAdapter",
]


def __getattr__(name):
    if name in {"PathResolver", "TopologyLoader"}:
        from .loader import PathResolver, TopologyLoader

        return {"PathResolver": PathResolver, "TopologyLoader": TopologyLoader}[name]
    if name == "TopologyValidator":
        from .validator import TopologyValidator

        return TopologyValidator
    if name in {"TopologyPlanner", "TopologyPlanningError", "PlanningError"}:
        from .planner import PlanningError, TopologyPlanner, TopologyPlanningError

        return {"TopologyPlanner": TopologyPlanner, "TopologyPlanningError": TopologyPlanningError, "PlanningError": PlanningError}[name]
    if name == "MininetTopologyAdapter":
        from .mininet_adapter import MininetTopologyAdapter

        return MininetTopologyAdapter
    if name == "RuntimeFactory":
        from .factory import RuntimeFactory

        return RuntimeFactory
    if name == "CommandDispatcher":
        from .command import CommandDispatcher

        return CommandDispatcher
    if name in {"ContainerService", "SFCService", "TopologyService", "VMService", "VNFService"}:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)
