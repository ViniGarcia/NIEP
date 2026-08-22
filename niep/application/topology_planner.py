"""Compatibility facade for the pure topology planner."""

from .planner import (
    ControllerPlan,
    EndpointId,
    EndpointKind,
    EndpointType,
    InterfaceAssignment,
    LinkKind,
    LinkPlan,
    LinkStrategy,
    NodePlan,
    PlanningDiagnostic,
    PlanningError,
    TopologyPlan,
    TopologyPlanner,
    TopologyPlanningError,
)

__all__ = [
    "ControllerPlan", "EndpointId", "EndpointKind", "EndpointType",
    "InterfaceAssignment", "LinkKind", "LinkPlan", "LinkStrategy", "NodePlan",
    "PlanningDiagnostic", "PlanningError", "TopologyPlan", "TopologyPlanner",
    "TopologyPlanningError",
]
