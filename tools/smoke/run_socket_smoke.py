#!/usr/bin/env python3
"""Run a NIEP socket smoke scenario.

This script must run inside the Vagrant VM with privileges because the daemon
will create Mininet and libvirt resources.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOCKET_PATH = "/tmp/niep-smoke.sock"

sys.path.insert(0, str(ROOT / "tools"))
from niepctl import send_request


def expect(response, ok, code):
    if response.get("ok") != ok or response.get("code") != code:
        raise AssertionError(str(response))


def wait_for_socket(path, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(path):
            return
        time.sleep(0.2)
    raise TimeoutError("socket was not created")


def main():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    daemon = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "niepd.py"), "--socket", SOCKET_PATH],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    try:
        wait_for_socket(SOCKET_PATH)

        response = send_request(SOCKET_PATH, "define", ["tutorial/examples/mininet-ping.json"])
        expect(response, True, "defined")

        response = send_request(SOCKET_PATH, "topoup", [])
        expect(response, True, "topology_up")

        response = send_request(SOCKET_PATH, "mininet", ["pingall"])
        expect(response, True, "mininet_result")
        if response.get("data", {}).get("dropped") != 0:
            raise AssertionError(str(response))

        response = send_request(SOCKET_PATH, "topodown", [])
        expect(response, True, "topology_down")

        print("[ OK ] socket")
        return 0
    finally:
        if daemon.poll() is None:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)


if __name__ == "__main__":
    raise SystemExit(main())
