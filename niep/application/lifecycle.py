"""Compatibility import for application lifecycle primitives.

The implementation lives in :mod:`niep.domain.lifecycle` so the domain
package remains independent from application services.  Existing callers may
continue importing ``niep.application.lifecycle``.
"""

from niep.domain.lifecycle import (
    InvalidTopologyTransition,
    NEEDS_FOLLOWUP,
    OperationJournal,
    OperationStep,
    OperationStepState,
    STATE_TRANSITIONS,
    StepState,
    TOPOLOGY_STATE_TRANSITIONS,
    TOPOLOGY_TRANSITIONS,
    TopologyState,
    TopologyStateMachine,
    VALID_TRANSITIONS,
    operation_key,
)

__all__ = [
    "InvalidTopologyTransition",
    "NEEDS_FOLLOWUP",
    "OperationJournal",
    "OperationStep",
    "OperationStepState",
    "STATE_TRANSITIONS",
    "StepState",
    "TOPOLOGY_STATE_TRANSITIONS",
    "TOPOLOGY_TRANSITIONS",
    "TopologyState",
    "TopologyStateMachine",
    "VALID_TRANSITIONS",
    "operation_key",
]
