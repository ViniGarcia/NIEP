#!/usr/bin/env python3
"""Run three Alpine VM startup checks through NIEP and Mininet."""

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


HERE = Path(__file__).resolve().parent
TOPOLOGY = HERE / "example" / "topology.json"
NIEPCTL = Path(sys.executable).with_name("niepctl")
READY_TIMEOUT = 30.0
HTTP_TIMEOUT = 1.0
POLL_INTERVAL = 0.2
RUNS = 3


def niep(*args, check=True):
    result = subprocess.run(
        [str(NIEPCTL if NIEPCTL.is_file() else shutil.which("niepctl") or "niepctl"), *args],
        text=True, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if check and result.returncode:
        raise RuntimeError(f"niepctl {' '.join(args)} failed:\n{result.stdout}")
    return result


def wait_for_http():
    deadline = time.monotonic() + READY_TIMEOUT
    while time.monotonic() < deadline:
        result = niep(
            "--json", "mininet", "cmd", "h1", "curl", "--noproxy", "10.20.0.2",
            "--silent", "--show-error", "--max-time", str(HTTP_TIMEOUT),
            "--output", "-", "--write-out", "%{http_code}",
            "http://10.20.0.2:8080/health", check=False,
        )
        if result.returncode == 0:
            response = json.loads(result.stdout)
            output = response.get("data", {}).get("output", "")
            if response.get("ok") and output.strip() == "ok200":
                return
        time.sleep(POLL_INTERVAL)
    raise TimeoutError(f"HTTP endpoint was not ready within {READY_TIMEOUT:g} seconds")


def run_once(number):
    ready = False
    defined = False
    startup_attempted = False
    try:
        niep("define", str(TOPOLOGY))
        defined = True
        start_ns = time.perf_counter_ns()
        startup_attempted = True
        niep("topoup")
        wait_for_http()
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000
        print(f"Run {number}: HTTP ready in {elapsed_ms:.1f} ms", flush=True)
        ready = True
    except Exception as exc:
        print(f"Run {number}: FAIL: {exc}", file=sys.stderr, flush=True)
        return False
    finally:
        if startup_attempted:
            result = niep("topodown", check=False)
            if result.returncode:
                ready = False
                print(f"Run {number}: topodown failed:\n{result.stdout}", file=sys.stderr)
        if defined:
            result = niep("topodestroy", check=False)
            if result.returncode:
                ready = False
                print(f"Run {number}: topodestroy failed:\n{result.stdout}", file=sys.stderr)
    return ready


def main():
    if not NIEPCTL.is_file() and shutil.which("niepctl") is None:
        raise SystemExit("niepctl was not found; install the project environment or add it to PATH")
    results = [run_once(number) for number in range(1, RUNS + 1)]
    succeeded = sum(results)
    print(f"Summary: {succeeded}/{RUNS} runs succeeded")
    return 0 if succeeded == RUNS else 1


if __name__ == "__main__":
    raise SystemExit(main())
