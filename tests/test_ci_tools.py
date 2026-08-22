"""Host-only tests for the deterministic CI validation helpers."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.ci import check_docs, check_privileged_history


pytestmark = pytest.mark.unit


def _history_payload(*runs: dict[str, str]) -> dict[str, object]:
    return {"required_runs": 2, "runs": list(runs)}


def test_privileged_history_accepts_complete_rows_and_counts_successes() -> None:
    errors, successful_ids, minimum = check_privileged_history.validate_payload(
        _history_payload(
            {"id": "100", "revision": "abc123", "scenario": "all", "status": "success"},
            {"id": "101", "revision": "def456", "scenario": "all", "status": "failure"},
        )
    )

    assert errors == []
    assert successful_ids == {"100"}
    assert minimum == 2


@pytest.mark.parametrize(
    ("row", "expected"),
    [
        ({"id": "100", "revision": "abc", "scenario": "all"}, "missing required fields"),
        (
            {"id": "100", "revision": "abc", "scenario": "all", "status": "flaky"},
            "status must be one of",
        ),
        (
            {"id": "", "revision": "abc", "scenario": "all", "status": "success"},
            "id must be a non-empty string",
        ),
        (
            {"id": "100", "revision": "abc", "scenario": "all", "status": "success"},
            "duplicates another run ID",
        ),
    ],
)
def test_privileged_history_rejects_invalid_rows(row: dict[str, str], expected: str) -> None:
    payload = _history_payload(row, {"id": "100", "revision": "def", "scenario": "all", "status": "success"})

    errors, successful_ids, _minimum = check_privileged_history.validate_payload(payload)

    assert any(expected in error for error in errors)
    assert successful_ids


def test_privileged_history_rejects_non_object_rows() -> None:
    errors, _successful_ids, _minimum = check_privileged_history.validate_payload(
        {"required_runs": 1, "runs": ["not an object"]}
    )

    assert errors == ["runs[0] must be an object"]


def test_docs_accepts_valid_same_file_fragment_and_rejects_missing_one(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    source.write_text(
        "# CI e integração\n\n[valid](#ci-e-integra%C3%A7%C3%A3o)\n[missing](#does-not-exist)\n",
        encoding="utf-8",
    )

    original_root = check_docs.ROOT
    check_docs.ROOT = tmp_path
    try:
        errors = check_docs.check_links([source])
    finally:
        check_docs.ROOT = original_root

    assert len(errors) == 1
    assert "missing anchor #does-not-exist" in errors[0]
    assert "valid" not in errors[0]


def test_docs_accepts_fragment_in_linked_file(tmp_path: Path) -> None:
    source = tmp_path / "README.md"
    target = tmp_path / "guide.md"
    source.write_text("[guide](guide.md#setup)\n", encoding="utf-8")
    target.write_text("## Setup\n", encoding="utf-8")

    original_root = check_docs.ROOT
    check_docs.ROOT = tmp_path
    try:
        errors = check_docs.check_links([source])
    finally:
        check_docs.ROOT = original_root

    assert errors == []
