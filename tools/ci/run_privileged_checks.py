#!/usr/bin/env python3
"""Run the Vagrant validation stages with separate logs and a JSON evidence report.

Run on the Vagrant host; every selected Make target runs its tests in the guest.
Provisioning, diagnostic collection and VM disposal belong to the caller so
diagnostics can still be collected after a failed stage.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import time


SCENARIOS = (
    "all",
    "mininet-isolated",
    "mininet-connected",
    "vm-host-link",
    "click-policy",
    "container-host-link",
    "container-router",
    "iperf-click-shaper",
)
COMPLETE_TARGETS = (
    "vm-test-static",
    "vm-test-command-dispatcher",
    "vm-test-errors",
    "vm-test-spec",
    "vm-test-integration",
    "vm-smoke-all",
)


def commands_for(scenario: str) -> tuple[str, list[list[str]]]:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario: {scenario}")
    if scenario == "all":
        return "complete", [["make", target, "INTEGRATION_ARGS=all"] for target in COMPLETE_TARGETS]
    if scenario == "iperf-click-shaper":
        return "throughput", [["make", "vm-test-iperf-shaper"]]
    return "partial", [["make", "vm-test-integration", f"INTEGRATION_ARGS={scenario}"]]


def git_output(*args: str) -> str | None:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    except OSError:
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def write_report(path: Path, report: dict) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def run_checks(scenario: str, output: Path, revision: str | None = None) -> int:
    scope, commands = commands_for(scenario)
    # Never overwrite evidence from a previous attempt, including a failed one.
    output.mkdir(parents=True, exist_ok=False)
    status = git_output("status", "--porcelain")
    report = {
        "schema_version": 1,
        "revision": revision or git_output("rev-parse", "HEAD"),
        "worktree_dirty": None if status is None else bool(status),
        "scenario": scenario,
        "scope": scope,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "stages": [
            {"command": command, "status": "not_run", "log": f"{command[1]}.log"}
            for command in commands
        ],
    }
    report_path = output / "summary.json"
    write_report(report_path, report)
    exit_code = 0
    for stage in report["stages"]:
        stage["status"] = "running"
        write_report(report_path, report)
        print(f"[RUN] {' '.join(stage['command'])} -> {output / stage['log']}", flush=True)
        started = time.monotonic()
        with (output / stage["log"]).open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(
                    stage["command"], stdout=log, stderr=subprocess.STDOUT, check=False
                )
                exit_code = result.returncode
                if exit_code < 0:
                    exit_code = 128 - exit_code
            except OSError as exc:
                log.write(f"Could not start stage: {exc}\n")
                exit_code = 127
        stage.update(
            exit_code=exit_code,
            duration_seconds=round(time.monotonic() - started, 3),
            status="success" if exit_code == 0 else "failure",
        )
        write_report(report_path, report)
        print(f"[{stage['status'].upper()}] {stage['command'][1]} ({exit_code})", flush=True)
        if exit_code:
            break
    report.update(
        status="success" if exit_code == 0 else "failure",
        finished_at=datetime.now(timezone.utc).isoformat(),
        exit_code=exit_code,
    )
    write_report(report_path, report)
    return exit_code


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, default="all")
    parser.add_argument("--output", type=Path, default=Path("build/ci/privileged"))
    parser.add_argument("--revision", help="source revision for a checkout without Git metadata")
    args = parser.parse_args()
    try:
        return run_checks(args.scenario, args.output, args.revision)
    except FileExistsError:
        parser.error(f"output already exists; choose a new directory: {args.output}")


if __name__ == "__main__":
    raise SystemExit(main())
