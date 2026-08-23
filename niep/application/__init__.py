"""Application services and command dispatch.

Imports are lazy because creating an application service may load an optional
runtime adapter.  This keeps package discovery and metadata tools usable on a
host without Mininet/libvirt/Docker.
"""

__all__ = [
    "CommandDispatcher",
    "CommandProtocolError",
    "CommandRequest",
    "CommandResponse",
    "CommandRouter",
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
    "MininetApplyError",
    "TopologyApplicationError",
    "InvalidTopologyTransition",
    "OperationJournal",
    "OperationStep",
    "OperationStepState",
    "TopologyState",
    "TopologyStateMachine",
    "TopologySession",
    "ExecutorSnapshot",
    "ExecutorTopologyPort",
    "LegacyExecutorAdapter",
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
    if name in {"MininetApplyError", "TopologyApplicationError"}:
        from .mininet_adapter import MininetApplyError, TopologyApplicationError

        return {
            "MininetApplyError": MininetApplyError,
            "TopologyApplicationError": TopologyApplicationError,
        }[name]
    if name in {
        "InvalidTopologyTransition",
        "OperationJournal",
        "OperationStep",
        "OperationStepState",
        "TopologyState",
        "TopologyStateMachine",
    }:
        from . import lifecycle

        return getattr(lifecycle, name)
    if name == "RuntimeFactory":
        from .factory import RuntimeFactory

        return RuntimeFactory
    if name == "CommandDispatcher":
        from .command import CommandDispatcher

        return CommandDispatcher
    if name in {"CommandProtocolError", "CommandRequest", "CommandResponse", "CommandRouter"}:
        from .command import CommandProtocolError, CommandRequest, CommandResponse, CommandRouter

        return {
            "CommandProtocolError": CommandProtocolError,
            "CommandRequest": CommandRequest,
            "CommandResponse": CommandResponse,
            "CommandRouter": CommandRouter,
        }[name]
    if name == "TopologySession":
        from .session import TopologySession

        return TopologySession
    if name in {"ExecutorSnapshot", "ExecutorTopologyPort", "LegacyExecutorAdapter"}:
        from .executor_port import ExecutorSnapshot, ExecutorTopologyPort, LegacyExecutorAdapter

        return {
            "ExecutorSnapshot": ExecutorSnapshot,
            "ExecutorTopologyPort": ExecutorTopologyPort,
            "LegacyExecutorAdapter": LegacyExecutorAdapter,
        }[name]
    if name in {"ContainerService", "SFCService", "TopologyService", "VMService", "VNFService"}:
        from . import service

        return getattr(service, name)
    raise AttributeError(name)
