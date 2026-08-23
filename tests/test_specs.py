"""Collectable wrapper around the legacy parser/spec validator."""

from __future__ import annotations

import pytest

from tools import check_specs


pytestmark = [pytest.mark.unit, pytest.mark.contract]


def test_tutorial_examples_produce_neutral_specs() -> None:
    """Keep the original check_specs assertions as the source of truth."""

    for name, relative_path in check_specs.EXAMPLES.items():
        path = (check_specs.ROOT / relative_path).resolve()
        errors = check_specs.check_example(name, str(path))
        assert errors == [], "\n".join(errors)


def test_tutorial_click_scripts_use_paths_from_repository_root() -> None:
    scripts = (
        "forward-start.ns",
        "forward-reload.ns",
        "policy-forward-start.ns",
        "policy-forward-reload.ns",
    )
    for filename in scripts:
        path = check_specs.ROOT / "tutorial/examples/click" / filename
        assert path.is_file(), path
        lines = path.read_text(encoding="utf-8").splitlines()
        post_function = next(line for line in lines if line.startswith("POST_FUNCTION "))
        target = post_function.split(maxsplit=1)[1]
        assert target.startswith("tutorial/examples/"), (path, target)
        assert (check_specs.ROOT / target).is_file(), (path, target)


def test_tutorial_docs_and_smokes_use_repository_root_as_cwd() -> None:
    paths = [
        check_specs.ROOT / "README.md",
        *sorted((check_specs.ROOT / "tutorial").glob("*.md")),
        check_specs.ROOT / "tools/check_specs.py",
        check_specs.ROOT / "tools/smoke/run_cli_smoke.py",
    ]
    for path in paths:
        text = path.read_text(encoding="utf-8")
        assert "../tutorial" not in text, path
    container_tutorial = (check_specs.ROOT / "tutorial/07-container-runtime.md").read_text(
        encoding="utf-8"
    )
    assert '"alpine-container.json"' in container_tutorial
    assert '"../tutorial/examples/alpine-container.json"' not in container_tutorial
    assert "chdir(ROOT)" in (check_specs.ROOT / "tools/check_specs.py").read_text(
        encoding="utf-8"
    )
    assert "cwd=ROOT" in (check_specs.ROOT / "tools/smoke/run_cli_smoke.py").read_text(
        encoding="utf-8"
    )
