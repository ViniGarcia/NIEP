"""Exercise CI stage orchestration using subprocesses without touching a VM."""

import json
from pathlib import Path
import sys

import pytest

from tools.ci.run_privileged_checks import run_checks


pytestmark = pytest.mark.unit


@pytest.fixture
def fake_make(tmp_path, monkeypatch):
    # The generated executable is a test double, not NIEP source. pytest-cov's
    # subprocess bootstrap otherwise reads its temporary cwd without pyproject
    # and produces statement-only data that cannot join the branch report.
    monkeypatch.delenv("COV_CORE_SOURCE", raising=False)
    executable = tmp_path / "make"
    executable.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "from pathlib import Path\n"
        "with Path(os.environ['CALLS_FILE']).open('a') as calls:\n"
        "    calls.write(' '.join(sys.argv[1:]) + '\\n')\n"
        "print('stage stdout', flush=True)\n"
        "print('stage stderr', file=sys.stderr, flush=True)\n"
        "sys.exit(23 if sys.argv[1] == os.environ.get('FAIL_TARGET') else 0)\n"
    )
    executable.chmod(0o755)
    calls = tmp_path / "calls.txt"
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("CALLS_FILE", str(calls))
    monkeypatch.chdir(tmp_path)
    return calls


def test_complete_run_covers_release_stages_and_preserves_logs(tmp_path, fake_make):
    output = tmp_path / "report"

    assert run_checks("all", output, "candidate-revision") == 0

    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "success"
    assert report["scope"] == "complete"
    assert report["revision"] == "candidate-revision"
    assert report["worktree_dirty"] is None  # An archive is not a verified clean Git checkout.
    assert fake_make.read_text().splitlines() == [
        "vm-test-static INTEGRATION_ARGS=all",
        "vm-test-command-dispatcher INTEGRATION_ARGS=all",
        "vm-test-errors INTEGRATION_ARGS=all",
        "vm-test-spec INTEGRATION_ARGS=all",
        "vm-test-integration INTEGRATION_ARGS=all",
        "vm-smoke-all INTEGRATION_ARGS=all",
    ]
    for stage in report["stages"]:
        assert stage["status"] == "success"
        assert stage["duration_seconds"] >= 0
        assert (output / stage["log"]).read_text() == "stage stdout\nstage stderr\n"


def test_failed_stage_stops_run_and_retains_original_exit_code(tmp_path, fake_make, monkeypatch):
    monkeypatch.setenv("FAIL_TARGET", "vm-test-errors")
    output = tmp_path / "report"

    assert run_checks("all", output) == 23

    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "failure"
    assert report["exit_code"] == 23
    assert [stage["status"] for stage in report["stages"]] == [
        "success",
        "success",
        "failure",
        "not_run",
        "not_run",
        "not_run",
    ]
    assert len(fake_make.read_text().splitlines()) == 3
    assert "stage stderr" in (output / "vm-test-errors.log").read_text()


@pytest.mark.parametrize(
    ("scenario", "scope", "command"),
    [
        ("container-router", "partial", "vm-test-integration INTEGRATION_ARGS=container-router"),
        ("iperf-click-shaper", "throughput", "vm-test-iperf-shaper"),
    ],
)
def test_partial_and_throughput_runs_are_not_complete(
    tmp_path, fake_make, scenario, scope, command
):
    output = tmp_path / "report"

    assert run_checks(scenario, output) == 0

    report = json.loads((output / "summary.json").read_text())
    assert report["scope"] == scope
    assert fake_make.read_text().splitlines() == [command]


def test_missing_make_records_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))
    output = tmp_path / "report"

    assert run_checks("all", output) == 127

    report = json.loads((output / "summary.json").read_text())
    assert report["status"] == "failure"
    assert report["stages"][1]["status"] == "not_run"
    assert "Could not start stage" in (output / "vm-test-static.log").read_text()


def test_previous_evidence_is_never_overwritten(tmp_path, fake_make):
    output = tmp_path / "report"
    output.mkdir()
    previous = output / "summary.json"
    previous.write_text("previous attempt\n")

    with pytest.raises(FileExistsError):
        run_checks("all", output)

    assert previous.read_text() == "previous attempt\n"
    assert not fake_make.exists()


def test_invalid_scenario_never_starts_a_command(tmp_path, fake_make):
    output = tmp_path / "report"
    with pytest.raises(ValueError, match="unknown scenario"):
        run_checks("all; touch unexpected", output)
    assert not fake_make.exists()
    assert not output.exists()
