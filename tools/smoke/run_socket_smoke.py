#!/usr/bin/env python3
"""Run a NIEP socket smoke scenario.

This script must run inside the Vagrant VM with privileges because the daemon
will create Mininet and libvirt resources.
"""

from __future__ import annotations

import grp
import json
import os
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

import pexpect


ROOT = Path(__file__).resolve().parents[2]
SOCKET_PATH = "/run/niep.sock"

from niep.interfaces.niepctl import receive_line, send_request


def niepctl_entrypoint() -> Path:
    """Return the console script installed beside this smoke's interpreter."""

    executable_name = "niepctl.exe" if os.name == "nt" else "niepctl"
    executable = Path(sys.executable).with_name(executable_name)
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise RuntimeError(
            "socket smoke requires the installed 'niepctl' entrypoint beside "
            f"{sys.executable}; install NIEP in that interpreter environment"
        )
    return executable


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


def run_shell_request(path, container_id, command):
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(path)
        request = {
            "command": "container",
            "args": ["shell", container_id, *command],
        }
        client.sendall((json.dumps(request) + "\n").encode("utf-8"))
        response, remaining = receive_line(client)
        output = remaining
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            output += chunk
        return response, output.decode("utf-8", "ignore")
    finally:
        client.close()


def expect_terminal(child, expected):
    while True:
        match = child.expect([expected, r"\x1b\[6n", pexpect.EOF])
        if match == 0:
            return
        if match == 1:
            child.send("\x1b[1;1R")
            continue
        raise AssertionError("container shell closed before expected output")


def expect_terminal_exit(child):
    while True:
        match = child.expect([r"\x1b\[6n", pexpect.EOF])
        if match == 0:
            child.send("\x1b[1;1R")
            continue
        return


def run_niepctl_shell(path):
    child = pexpect.spawn(
        str(niepctl_entrypoint()),
        [
            "--socket",
            path,
            "container",
            "shell",
            "doc-alpine",
        ],
        cwd=ROOT,
        encoding="utf-8",
        timeout=20,
    )
    try:
        expect_terminal(child, r"(?:^|\r\n)[^\r\n]*[#$] ")
        child.sendline("echo NIEPCTL_SHELL_OK")
        expect_terminal(child, r"(?:^|\r\n)NIEPCTL_SHELL_OK\r\n")
        expect_terminal(child, r"(?:^|\r\n)[^\r\n]*[#$] ")
        child.sendline("exit")
        expect_terminal_exit(child)
    finally:
        if child.isalive():
            child.close(force=True)


def complete_niepctl(path, words, current_word):
    environment = os.environ.copy()
    environment.update(
        {
            "NIEP_SOCKET": path,
            "COMP_WORDS": words,
            "COMP_CWORD": str(current_word),
            "_NIEPCTL_COMPLETE": "complete_bash",
        }
    )
    completed = subprocess.run(
        [str(niepctl_entrypoint())],
        cwd=ROOT,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=20,
    )
    if completed.returncode != 0:
        raise AssertionError(completed.stdout)
    return completed.stdout


def run_legacy_cli_container_access():
    child = pexpect.spawn(
        sys.executable,
        [str(ROOT / "CLI" / "CLI.py")],
        cwd=ROOT,
        encoding="utf-8",
        timeout=30,
    )
    try:
        child.expect("niep> ")
        child.sendline("define tutorial/examples/container-host-link.json")
        child.expect("niep> ")
        child.sendline("topoup")
        child.expect("niep> ")
        child.sendline("container doc-alpine")
        child.expect(r"container\(doc-alpine\)> ")
        child.sendline("containerexec printf NIEP_LEGACY_EXEC_OK")
        child.expect("NIEP_LEGACY_EXEC_OK")
        child.expect(r"container\(doc-alpine\)> ")
        child.sendline("containershell")
        child.sendline("echo NIEP_LEGACY_SHELL_OK")
        child.expect("NIEP_LEGACY_SHELL_OK")
        child.sendline("exit")
        child.expect(r"container\(doc-alpine\)> ")
        child.sendline("exit")
        child.expect("niep> ")
        child.sendline("topodown")
        child.expect("niep> ")
        child.sendline("exit")
        child.expect(pexpect.EOF)
    finally:
        if child.isalive():
            child.close(force=True)


def main():
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)

    daemon = subprocess.Popen(
        [sys.executable, str(ROOT / "tools" / "niepd.py")],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )

    try:
        wait_for_socket(SOCKET_PATH)
        socket_mode = stat.S_IMODE(os.stat(SOCKET_PATH).st_mode)
        if socket_mode != 0o660:
            raise AssertionError(
                "unexpected socket mode: " + oct(socket_mode) + " (expected 0o660)"
            )
        socket_stat = os.stat(SOCKET_PATH)
        expected_group = grp.getgrnam("niep")
        if socket_stat.st_uid != 0 or socket_stat.st_gid != expected_group.gr_gid:
            raise AssertionError(
                "unexpected socket owner: "
                + str(socket_stat.st_uid)
                + ":"
                + str(socket_stat.st_gid)
                + " (expected 0:"
                + str(expected_group.gr_gid)
                + ")"
            )

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

        response = send_request(SOCKET_PATH, "define", ["tutorial/examples/container-host-link.json"])
        expect(response, True, "defined")

        response = send_request(SOCKET_PATH, "topoup", [])
        expect(response, True, "topology_up")

        client = subprocess.run(
            [
                str(niepctl_entrypoint()),
                "--json",
                "status",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
        if client.returncode != 0:
            raise AssertionError(client.stdout)
        status_response = json.loads(client.stdout)
        if "doc-alpine" not in status_response.get("data", {}).get("containers", []):
            raise AssertionError(client.stdout)

        completion = complete_niepctl(
            SOCKET_PATH,
            "niepctl container exec doc-",
            3,
        )
        if "doc-alpine" not in completion:
            raise AssertionError("container completion missing: " + repr(completion))

        response = send_request(
            SOCKET_PATH,
            "container",
            ["exec", "doc-alpine", "printf", "NIEP_EXEC_OK"],
        )
        expect(response, True, "container_exec")
        if response.get("data", {}).get("output") != "NIEP_EXEC_OK":
            raise AssertionError(str(response))

        client = subprocess.run(
            [
                str(niepctl_entrypoint()),
                "--socket",
                SOCKET_PATH,
                "container",
                "exec",
                "doc-alpine",
                "ip",
                "-o",
                "addr",
                "show",
                "eth0",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
        if client.returncode != 0 or "10.60.0.2/24" not in client.stdout:
            raise AssertionError(client.stdout)

        client = subprocess.run(
            [
                str(niepctl_entrypoint()),
                "--socket",
                SOCKET_PATH,
                "container",
                "exec",
                "doc-alpine",
                "/bin/sh",
                "-c",
                "exit 7",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
        if client.returncode != 7:
            raise AssertionError("unexpected container exec status: " + str(client.returncode) + "\n" + client.stdout)

        response, output = run_shell_request(
            SOCKET_PATH,
            "doc-alpine",
            ["/bin/sh", "-c", "printf NIEP_SHELL_OK"],
        )
        expect(response, True, "container_shell")
        if "NIEP_SHELL_OK" not in output:
            raise AssertionError(repr(output))

        run_niepctl_shell(SOCKET_PATH)

        response = send_request(SOCKET_PATH, "topodown", [])
        expect(response, True, "topology_down")

        response = send_request(SOCKET_PATH, "define", ["tutorial/examples/vm-basic.json"])
        expect(response, True, "defined")

        response = send_request(SOCKET_PATH, "topoup", [])
        expect(response, True, "topology_up")

        completion = complete_niepctl(
            SOCKET_PATH,
            "niepctl vm management doc-",
            3,
        )
        if "doc-tinycore" not in completion:
            raise AssertionError("VM completion missing: " + repr(completion))

        response = send_request(SOCKET_PATH, "topodown", [])
        expect(response, True, "topology_down")

        run_legacy_cli_container_access()

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
