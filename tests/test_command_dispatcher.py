"""Host-only, collectable coverage for command dispatch validation."""

from __future__ import annotations

import pytest

from tools import check_command_dispatcher


pytestmark = pytest.mark.unit


def test_command_dispatcher_legacy_assertions_execute() -> None:
    """The target must run assertions, not merely compile Python files."""

    assert check_command_dispatcher.run_checks() == 0
