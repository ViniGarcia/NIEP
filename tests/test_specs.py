"""Collectable wrapper around the legacy parser/spec validator."""

from __future__ import annotations

import pytest

from tools import check_specs


pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_tutorial_examples_produce_neutral_specs() -> None:
    """Keep the original check_specs assertions as the source of truth."""

    for name, relative_path in check_specs.EXAMPLES.items():
        path = (check_specs.ROOT / "CLI" / relative_path).resolve()
        errors = check_specs.check_example(name, str(path))
        assert errors == [], "\n".join(errors)
