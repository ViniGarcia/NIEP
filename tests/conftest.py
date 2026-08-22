"""Pytest bootstrap for the host-only baseline."""

from dataclasses import dataclass, field
from typing import Any

import pytest

try:
    from tests.support import install_optional_dependency_stubs
except ImportError:  # pragma: no cover - direct pytest invocation fallback
    from support import install_optional_dependency_stubs


install_optional_dependency_stubs()


@dataclass
class RecordedCommands:
    """Deterministic command double for tests that should not touch the host."""

    calls: list[tuple[Any, ...]] = field(default_factory=list)
    result: Any = ""

    def run(self, *command: Any, **_kwargs: Any) -> Any:
        self.calls.append(tuple(command))
        return self.result


@dataclass
class FakeClock:
    """Small controllable clock for timeout and retry characterization."""

    now: float = 0.0

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> float:
        self.now += seconds
        return self.now


@pytest.fixture
def filesystem(tmp_path):
    """Temporary filesystem root with automatic cleanup."""

    return tmp_path


@pytest.fixture
def system_commands():
    """Recorder suitable for injecting in place of subprocess helpers."""

    return RecordedCommands()


@pytest.fixture
def clock():
    """Controllable monotonic-style clock with no wall-clock sleeping."""

    return FakeClock()


@pytest.fixture
def runtime(system_commands):
    """Minimal runtime seam whose operations are observable and host-safe."""

    return system_commands
