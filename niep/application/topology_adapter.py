"""Compatibility facade for the Mininet topology adapter."""

from .mininet_adapter import (
    AppliedTopology,
    MininetApplyError,
    MininetTopologyAdapter,
    TopologyApplicationError,
)

__all__ = [
    "AppliedTopology",
    "MininetApplyError",
    "MininetTopologyAdapter",
    "TopologyApplicationError",
]
