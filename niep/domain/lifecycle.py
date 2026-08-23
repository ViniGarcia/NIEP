"""Transactional topology lifecycle primitives.

The runtime adapters in :mod:`niep.runtime` intentionally keep their legacy
numeric status attributes.  These domain types provide the application-owned
source of truth for topology lifecycle state and operation progress.  They are
deliberately in-memory: a daemon restart must reconcile resources with the
adapters before an operation journal can safely be persisted.
"""

from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import json
from typing import Any

from niep.runtime.errors import cleanup_failure_record


class TopologyState(str, Enum):
    """Application lifecycle states for one materialized topology."""

    UNDEFINED = "undefined"
    DEFINED = "defined"
    STARTING = "starting"
    UP = "up"
    STOPPING = "stopping"
    DOWN = "down"
    DESTROYED = "destroyed"
    FAILED = "failed"
    CLEANUP_PENDING = "cleanup_pending"


# State transitions are explicit and intentionally kept as a data table.  A
# public command may implement an idempotent no-op (for example ``down`` from
# DOWN), but it must never silently move through an unlisted state.
TOPOLOGY_TRANSITIONS: dict[TopologyState, frozenset[TopologyState]] = {
    TopologyState.UNDEFINED: frozenset({TopologyState.DEFINED}),
    TopologyState.DEFINED: frozenset(
        {TopologyState.STARTING, TopologyState.DOWN, TopologyState.UNDEFINED, TopologyState.DESTROYED}
        | {TopologyState.CLEANUP_PENDING}
    ),
    TopologyState.STARTING: frozenset(
        {TopologyState.UP, TopologyState.FAILED, TopologyState.CLEANUP_PENDING, TopologyState.UNDEFINED}
    ),
    TopologyState.UP: frozenset(
        {TopologyState.STOPPING, TopologyState.FAILED}
    ),
    TopologyState.STOPPING: frozenset(
        {TopologyState.DOWN, TopologyState.FAILED, TopologyState.CLEANUP_PENDING}
    ),
    TopologyState.DOWN: frozenset(
        {
            TopologyState.STARTING,
            TopologyState.DEFINED,
            TopologyState.UNDEFINED,
            TopologyState.DESTROYED,
            TopologyState.CLEANUP_PENDING,
        }
    ),
    TopologyState.DESTROYED: frozenset({TopologyState.DEFINED}),
    TopologyState.FAILED: frozenset(
        {
            TopologyState.STARTING,
            TopologyState.DEFINED,
            TopologyState.UNDEFINED,
            TopologyState.DOWN,
            TopologyState.CLEANUP_PENDING,
        }
    ),
    TopologyState.CLEANUP_PENDING: frozenset(
        {
            TopologyState.STOPPING,
            TopologyState.DOWN,
            TopologyState.FAILED,
            TopologyState.DEFINED,
            TopologyState.DESTROYED,
        }
    ),
}

# Public aliases make the table discoverable without coupling clients to one
# historical spelling.
STATE_TRANSITIONS = TOPOLOGY_TRANSITIONS
TOPOLOGY_STATE_TRANSITIONS = TOPOLOGY_TRANSITIONS
VALID_TRANSITIONS = TOPOLOGY_TRANSITIONS


class InvalidTopologyTransition(ValueError):
    """Raised when a state transition is not present in the transition table."""

    def __init__(self, current: TopologyState, target: TopologyState) -> None:
        self.current = current
        self.target = target
        super().__init__(f"invalid topology transition: {current.value} -> {target.value}")


class TopologyStateMachine:
    """Small validated state holder used by application services."""

    def __init__(self, state: TopologyState = TopologyState.UNDEFINED) -> None:
        self.state = TopologyState(state)
        self.history: list[TopologyState] = [self.state]

    def can_transition(self, target: TopologyState) -> bool:
        target = TopologyState(target)
        return target in TOPOLOGY_TRANSITIONS[self.state]

    def transition(self, target: TopologyState) -> TopologyState:
        target = TopologyState(target)
        if not self.can_transition(target):
            raise InvalidTopologyTransition(self.state, target)
        self.state = target
        self.history.append(target)
        return self.state

    def force(self, state: TopologyState) -> TopologyState:
        """Set a reconciled state at an adapter boundary.

        This is reserved for materialization/reconciliation, where no runtime
        operation is being performed.  Normal commands must use ``transition``.
        """

        self.state = TopologyState(state)
        self.history.append(self.state)
        return self.state


class OperationStepState(str, Enum):
    """Progress of one operation step."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    CLEANUP_PENDING = "cleanup_pending"
    SKIPPED = "skipped"


# A shorter name is convenient for callers and mirrors TopologyState.
StepState = OperationStepState


class _NeedsFollowup:
    """Internal marker for legacy create operations that require ``apply``."""


NEEDS_FOLLOWUP = _NeedsFollowup()


def operation_key(
    operation: str,
    resource_type: str = "topology",
    resource_id: Any = "topology",
    *,
    namespace: str = "topology",
) -> str:
    """Build a stable, human-readable operation key.

    The key has no process identity or object address, so rebuilding a plan for
    the same topology resumes the same logical steps.  Values are JSON encoded
    when possible and otherwise converted to bounded strings.
    """

    def stable(value: Any) -> str:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return str(value)
        try:
            return json.dumps(value, sort_keys=True, separators=(",", ":"))
        except (TypeError, ValueError):
            return str(value)

    raw = ":".join((str(namespace), str(resource_type), stable(resource_id), str(operation)))
    # Human-readable keys are preferable in diagnostics.  Hash only very long
    # or unsafe identifiers while retaining an unambiguous prefix.
    if len(raw) <= 240 and all(char.isalnum() or char in "_:.-/" for char in raw):
        return raw
    digest = hashlib.sha256(raw.encode("utf-8", "replace")).hexdigest()[:16]
    return f"{namespace}:{resource_type}:{digest}:{operation}"


def _success(value: Any) -> bool:
    """Interpret one adapter result at the operation boundary.

    Legacy adapters use ``None``, ``True`` and numeric zero for success.  The
    conversion happens here, once; application services consume step state and
    never inspect numeric executor status values.
    """

    return value is None or value is True or (isinstance(value, int) and not isinstance(value, bool) and value == 0)


def _json_safe(value: Any, depth: int = 0) -> Any:
    """Bound operation results/metadata to JSON-safe deterministic values."""

    if depth > 4:
        return "<truncated>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, depth + 1) for item in value[:100]]
    if isinstance(value, dict):
        return {
            str(key): _json_safe(item, depth + 1)
            for key, item in list(value.items())[:100]
        }
    return str(value)


@dataclass
class OperationStep:
    """One idempotent operation and its optional compensation.

    ``apply`` and ``compensate`` are callables owned by the orchestrator, not
    runtime adapters.  A step is considered complete only after its apply
    callable returns a successful result.  Completed steps are never applied
    again by :meth:`OperationJournal.run`.
    """

    operation: str
    resource_type: str = "topology"
    resource_id: Any = "topology"
    apply: Callable[[], Any] | None = None
    compensate: Callable[[], Any] | None = None
    depends_on: tuple[str, ...] = ()
    key: str | None = None
    state: OperationStepState = OperationStepState.PENDING
    attempts: int = 0
    compensation_attempts: int = 0
    result: Any = None
    error: dict[str, Any] | None = None
    compensation_error: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.operation = str(self.operation)
        self.resource_type = str(self.resource_type)
        self.key = self.key or operation_key(
            self.operation,
            self.resource_type,
            self.resource_id,
        )
        self.depends_on = tuple(str(item) for item in self.depends_on)
        self.state = OperationStepState(self.state)

    @property
    def name(self) -> str:
        return self.operation

    @name.setter
    def name(self, value: str) -> None:
        self.operation = str(value)

    @property
    def resource(self) -> str:
        return self.resource_type

    @property
    def status(self) -> OperationStepState:
        """Compatibility alias used by journal consumers."""

        return self.state

    @status.setter
    def status(self, value: OperationStepState) -> None:
        self.state = OperationStepState(value)

    @property
    def complete(self) -> bool:
        return self.state in {OperationStepState.COMPLETED, OperationStepState.SKIPPED}

    @property
    def incomplete(self) -> bool:
        return not self.complete

    @property
    def attempted(self) -> bool:
        """Whether apply was entered and may have left partial resources."""

        return self.attempts > 0

    def mark_skipped(self, result: Any = None) -> None:
        self.state = OperationStepState.SKIPPED
        self.result = result
        self.error = None

    def _failure(self, error: Any) -> dict[str, Any]:
        return cleanup_failure_record(
            error,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            operation=self.operation,
        )

    def run(self) -> bool:
        """Run this step once, or retry it if it is incomplete."""

        if self.complete:
            return True
        if self.apply is None:
            self.state = OperationStepState.COMPLETED
            self.result = None
            self.error = None
            return True
        self.state = OperationStepState.RUNNING
        self.attempts += 1
        try:
            result = self.apply()
            self.result = result
            if not _success(result):
                raise RuntimeError(f"{self.operation} returned unsuccessful result: {result}")
            self.error = None
            self.state = OperationStepState.COMPLETED
            return True
        except Exception as exc:  # noqa: BLE001 - journal must retain every failure
            self.error = self._failure(exc)
            self.state = OperationStepState.FAILED
            return False

    def run_compensation(self) -> bool:
        """Compensate a completed step, retaining failures for retry."""

        if self.state in {
            OperationStepState.PENDING,
            OperationStepState.COMPENSATED,
            OperationStepState.SKIPPED,
        }:
            return True
        if self.state == OperationStepState.FAILED and not self.attempted:
            return True
        if self.compensate is None:
            self.state = OperationStepState.COMPENSATED
            return True
        self.state = OperationStepState.COMPENSATING
        self.compensation_attempts += 1
        try:
            result = self.compensate()
            if not _success(result):
                raise RuntimeError(f"{self.operation} compensation returned unsuccessful result: {result}")
            self.compensation_error = None
            self.state = OperationStepState.COMPENSATED
            return True
        except Exception as exc:  # noqa: BLE001 - best effort compensation
            self.compensation_error = self._failure(exc)
            self.state = OperationStepState.CLEANUP_PENDING
            return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "operation": self.operation,
            "resource_type": self.resource_type,
            "resource_id": str(self.resource_id),
            "depends_on": list(self.depends_on),
            "state": self.state.value,
            "attempts": self.attempts,
            "compensation_attempts": self.compensation_attempts,
            "result": _json_safe(self.result),
            "error": self.error,
            "compensation_error": self.compensation_error,
            "metadata": _json_safe(self.metadata),
        }


class OperationJournal:
    """Ordered in-memory operation ledger with deterministic retry behavior."""

    def __init__(self, steps: Iterable[OperationStep] | None = None) -> None:
        self._steps: OrderedDict[str, OperationStep] = OrderedDict()
        self.history: list[dict[str, Any]] = []
        if steps:
            for step in steps:
                self.add(step)

    @property
    def steps(self) -> tuple[OperationStep, ...]:
        return tuple(self._steps.values())

    @property
    def entries(self) -> tuple[OperationStep, ...]:
        return self.steps

    def __iter__(self):
        return iter(self._steps.values())

    def __len__(self) -> int:
        return len(self._steps)

    def add(self, step: OperationStep) -> OperationStep:
        if not isinstance(step, OperationStep):
            raise TypeError("journal entries must be OperationStep instances")
        if step.key in self._steps:
            existing = self._steps[step.key]
            # A retry rebuild may provide fresh bound callables; progress and
            # attempts remain in the existing entry.
            existing.apply = step.apply
            existing.compensate = step.compensate
            existing.depends_on = step.depends_on
            existing.metadata.update(step.metadata)
            return existing
        self._steps[step.key] = step
        return step

    register = add
    record = add
    add_step = add

    def __getitem__(self, key: str) -> OperationStep:
        return self.require(key)

    def get(self, key: str, default: OperationStep | None = None) -> OperationStep | None:
        return self._steps.get(str(key), default)

    get_step = get

    def require(self, key: str) -> OperationStep:
        try:
            return self._steps[str(key)]
        except KeyError as exc:
            raise KeyError(f"unknown operation step: {key}") from exc

    @property
    def completed(self) -> tuple[OperationStep, ...]:
        return tuple(step for step in self if step.complete)

    @property
    def incomplete(self) -> tuple[OperationStep, ...]:
        # COMPENSATED is intentionally included: the forward operation is no
        # longer active and must be reapplied if this same journal resumes a
        # startup after cleanup.
        return tuple(step for step in self if step.incomplete)

    @property
    def failed(self) -> tuple[OperationStep, ...]:
        return tuple(step for step in self if step.state == OperationStepState.FAILED)

    @property
    def cleanup_pending(self) -> tuple[OperationStep, ...]:
        return tuple(step for step in self if step.state == OperationStepState.CLEANUP_PENDING)

    def _dependencies_ready(self, step: OperationStep) -> bool:
        return all(
            self.require(dependency).complete
            for dependency in step.depends_on
        )

    def run(self, *, stop_on_failure: bool = True) -> bool:
        """Apply pending/incomplete steps in declared dependency order."""

        for step in self:
            if step.complete:
                continue
            if not self._dependencies_ready(step):
                step.error = step._failure(
                    RuntimeError("operation dependency is incomplete")
                )
                step.state = OperationStepState.FAILED
                if stop_on_failure:
                    return False
                continue
            if not step.run() and stop_on_failure:
                return False
        return not self.failed

    def compensate(self, *, best_effort: bool = True) -> bool:
        """Compensate completed steps in reverse dependency/order sequence."""

        ok = True
        # Reversing registration order is deterministic; dependencies are
        # honored even when callers register independent steps in any order.
        pending = [
            step
            for step in self._steps.values()
            if (
                step.complete
                or step.state == OperationStepState.CLEANUP_PENDING
                or (step.state == OperationStepState.FAILED and step.attempted and step.compensate is not None)
            )
        ]
        while pending:
            eligible = [
                step
                for step in pending
                if not any(
                    other in pending and step.key in other.depends_on
                    for other in pending
                )
            ]
            if not eligible:
                eligible = [pending[-1]]
            for step in reversed(eligible):
                pending.remove(step)
                if not step.run_compensation():
                    ok = False
                    if not best_effort:
                        return False
        return ok

    def reset_incomplete(self) -> None:
        """Prepare failed/incomplete steps for retry without touching success."""

        for step in self:
            if step.state in {OperationStepState.FAILED, OperationStepState.RUNNING}:
                step.state = OperationStepState.PENDING

    def clear(self) -> None:
        self._steps.clear()
        self.history.clear()

    def to_dict(self) -> dict[str, Any]:
        return {"steps": [step.to_dict() for step in self], "incomplete": [step.key for step in self.incomplete]}

    as_dict = to_dict


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
