#!/usr/bin/env python3
"""Run NIEP CLI smoke scenarios non-interactively.

This runner is meant to be executed inside the Vagrant VM because the scenarios
need Mininet, libvirt, bridges, and sudo privileges.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI_DIR = ROOT / "CLI"


@dataclass(frozen=True)
class Step:
    command: str
    delay_after: float = 0


@dataclass(frozen=True)
class Scenario:
    name: str
    commands: list[Step]
    expected: list[str]
    timeout: int = 180


SCENARIOS = {
    "mininet": Scenario(
        name="mininet",
        commands=[
            Step("define ../tutorial/examples/mininet-ping.json"),
            Step("topoup", delay_after=2),
            Step("mininet"),
            Step("pingall"),
            Step("exit"),
            Step("topodown"),
            Step("exit"),
        ],
        expected=[
            "*** Results: 0% dropped",
        ],
        timeout=120,
    ),
    "vm": Scenario(
        name="vm",
        commands=[
            Step("define ../tutorial/examples/vm-basic.json"),
            Step("topoup", delay_after=20),
            Step("vm doc-tinycore"),
            Step("vmmanagement"),
            Step("exit"),
            Step("topodown"),
            Step("exit"),
        ],
        expected=[
            r"re:192\.168\.122\.\d+",
        ],
        timeout=180,
    ),
    "click": Scenario(
        name="click",
        commands=[
            Step("define ../tutorial/examples/click-forward-topology.json"),
            Step("topoup", delay_after=25),
            Step("vnf click-forward"),
            Step("vnfaction POST_FUNCTION ../tutorial/examples/click/policy-forward.click"),
            Step("vnfaction POST_START", delay_after=2),
            Step("exit"),
            Step("mininet"),
            Step("pingall"),
            Step("exit"),
            Step("topodown"),
            Step("exit"),
        ],
        expected=[
            "SUCCESS [200]",
            "*** Results: 33% dropped",
        ],
        timeout=240,
    ),
}


def run_scenario(scenario: Scenario) -> tuple[int, str]:
    proc = subprocess.Popen(
        ["sudo", "python3", "CLI.py"],
        cwd=CLI_DIR,
        text=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )

    assert proc.stdin is not None
    for step in scenario.commands:
        proc.stdin.write(step.command + "\n")
        proc.stdin.flush()
        if step.delay_after:
            time.sleep(step.delay_after)
    proc.stdin.close()
    proc.stdin = None

    output, _ = proc.communicate(timeout=scenario.timeout)
    returncode = proc.returncode
    return returncode, output


def assert_expected(scenario: Scenario, output: str) -> list[str]:
    missing: list[str] = []
    for expected in scenario.expected:
        if expected.startswith("re:"):
            if not re.search(expected[3:], output):
                missing.append(expected)
        elif expected not in output:
            missing.append(expected)
    return missing


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NIEP CLI smoke scenarios")
    parser.add_argument(
        "scenario",
        choices=sorted([*SCENARIOS.keys(), "all"]),
        help="Scenario to run",
    )
    parser.add_argument(
        "--show-output",
        action="store_true",
        help="Print full CLI output even when the scenario succeeds",
    )
    args = parser.parse_args()

    scenario_names = sorted(SCENARIOS) if args.scenario == "all" else [args.scenario]
    failed = False

    for name in scenario_names:
        scenario = SCENARIOS[name]
        print(f"[RUN ] {name}")
        try:
            returncode, output = run_scenario(scenario)
        except subprocess.TimeoutExpired as exc:
            failed = True
            print(f"[FAIL] {name}: timed out after {scenario.timeout}s")
            if exc.stdout:
                print(exc.stdout)
            continue

        missing = assert_expected(scenario, output)
        if returncode != 0 or missing:
            failed = True
            print(f"[FAIL] {name}: returncode={returncode}")
            if missing:
                print("[FAIL] missing expected output:")
                for item in missing:
                    print(f"  - {item}")
            print(output)
        else:
            print(f"[ OK ] {name}")
            if args.show_output:
                print(output)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
