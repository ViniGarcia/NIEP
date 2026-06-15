#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CLI_DIR = ROOT / "CLI"
sys.path.insert(0, str(ROOT / "TOPO-MAN"))
sys.path.insert(0, str(ROOT / "VEM"))

from Command import CommandDispatcher


@dataclass(frozen=True)
class Scenario:
    name: str
    run: object


class TestFailure(Exception):
    pass


def assert_result(result, code=None, ok=True):
    if result.ok != ok:
        raise TestFailure(str(result.to_dict()))
    if code is not None and result.code.value != code:
        raise TestFailure(str(result.to_dict()))
    return result


def assert_contains(value, expected):
    if expected not in value:
        raise TestFailure("missing " + repr(expected) + " in " + repr(value))


def dispatch(dispatcher, command, args=None, code=None):
    result = dispatcher.dispatch(command, args or [])
    return assert_result(result, code=code)


def mininet_cmd(dispatcher, node, command):
    result = dispatch(dispatcher, "mininet", ["cmd", node, command], code="node_command")
    return result.data["output"]


def mininet_probe(dispatcher, node, command):
    output = mininet_cmd(dispatcher, node, command + " >/dev/null 2>&1 && echo OK || echo FAIL")
    return "OK" in output.split()


def wait_for_vm_management(dispatcher, vm_id, attempts=12):
    for _ in range(attempts):
        result = dispatcher.dispatch("vm", ["management", vm_id])
        if result.ok:
            return result.data
        time.sleep(2)
    raise TestFailure("VM management address not available: " + str(result.to_dict()))


def ssh_vm(ip_address, command):
    ssh_command = [
        "sshpass",
        "-p",
        "NIEPvm00",
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "tc@" + ip_address,
        command,
    ]
    completed = subprocess.run(
        ssh_command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=30,
    )
    if completed.returncode != 0:
        raise TestFailure(completed.stdout)
    return completed.stdout


def run_topology(definition_path, body):
    dispatcher = CommandDispatcher()
    try:
        dispatch(dispatcher, "define", [definition_path], code="defined")
        dispatch(dispatcher, "topoup", code="topology_up")
        return body(dispatcher)
    finally:
        dispatcher.dispatch("topodown")


def isolated_mininet_hosts():
    def body(dispatcher):
        status = dispatch(dispatcher, "status", code="status")
        if status.data["up"] is not True:
            raise TestFailure(str(status.to_dict()))

        h1_addr = mininet_cmd(dispatcher, "h1", "ip -o addr show")
        h2_addr = mininet_cmd(dispatcher, "h2", "ip -o addr show")
        assert_contains(h1_addr, "10.40.0.1/24")
        assert_contains(h2_addr, "10.40.0.2/24")

        if mininet_probe(dispatcher, "h1", "ping -c1 -W1 10.40.0.2"):
            raise TestFailure("isolated h1 unexpectedly reached h2")

    run_topology("../tests/topologies/mininet-isolated-hosts.json", body)


def connected_mininet_hosts():
    def body(dispatcher):
        pingall = dispatch(dispatcher, "mininet", ["pingall"], code="mininet_result")
        if pingall.data["dropped"] != 0:
            raise TestFailure(str(pingall.to_dict()))

        if not mininet_probe(dispatcher, "h1", "ping -c1 -W1 10.10.0.2"):
            raise TestFailure("h1 did not reach h2")

    run_topology("../tests/topologies/mininet-connected-hosts.json", body)


def vm_host_link():
    def body(dispatcher):
        vm_list = dispatch(dispatcher, "vm", ["list"], code="defined")
        if vm_list.data != ["doc-tinycore-link"]:
            raise TestFailure(str(vm_list.to_dict()))

        management_ip = wait_for_vm_management(dispatcher, "doc-tinycore-link")
        ssh_vm(
            management_ip,
            "sudo ifconfig eth1 10.20.0.2 netmask 255.255.255.0 up || ifconfig eth1 10.20.0.2 netmask 255.255.255.0 up",
        )
        output = ssh_vm(management_ip, "ifconfig eth1")
        assert_contains(output, "10.20.0.2")

        if not mininet_probe(dispatcher, "h1", "ping -c1 -W2 10.20.0.2"):
            raise TestFailure("h1 did not reach VM data interface")

    run_topology("../tests/topologies/vm-host-link.json", body)


def click_policy_vnf():
    def body(dispatcher):
        vnf_list = dispatch(dispatcher, "vnf", ["list"], code="defined")
        if vnf_list.data != ["click-forward"]:
            raise TestFailure(str(vnf_list.to_dict()))

        dispatch(
            dispatcher,
            "vnf",
            ["action", "click-forward", "POST_FUNCTION", "../tests/fixtures/click/policy-forward.click"],
            code="vnf_action",
        )
        dispatch(dispatcher, "vnf", ["action", "click-forward", "POST_START"], code="vnf_action")
        time.sleep(2)

        if not mininet_probe(dispatcher, "h1", "ping -c1 -W2 10.30.0.2"):
            raise TestFailure("h1 did not reach h2 through VNF")
        if not mininet_probe(dispatcher, "h2", "ping -c1 -W2 10.30.0.3"):
            raise TestFailure("h2 did not reach h3 through switch")
        if mininet_probe(dispatcher, "h1", "ping -c1 -W2 10.30.0.3"):
            raise TestFailure("h1 unexpectedly reached h3")

        pingall = dispatch(dispatcher, "mininet", ["pingall"], code="mininet_result")
        if not 33 <= pingall.data["dropped"] <= 34:
            raise TestFailure(str(pingall.to_dict()))

    run_topology("../tests/topologies/click-policy-vnf.json", body)


def container_host_link():
    def body(dispatcher):
        container_list = dispatch(dispatcher, "container", ["list"], code="defined")
        if container_list.data != ["test-alpine"]:
            raise TestFailure(str(container_list.to_dict()))

        container_ip = dispatch(dispatcher, "container", ["exec", "test-alpine", "ip", "-o", "addr", "show", "eth0"], code="container_exec")
        assert_contains(container_ip.data["output"], "10.50.0.2/24")

        if not mininet_probe(dispatcher, "h1", "ping -c1 -W2 10.50.0.2"):
            raise TestFailure("h1 did not reach container interface")

        container_ping = dispatch(dispatcher, "container", ["exec", "test-alpine", "ping", "-c1", "-W2", "10.50.0.1"], code="container_exec")
        if container_ping.data["exit_code"] != 0:
            raise TestFailure(str(container_ping.to_dict()))

    run_topology("../tests/topologies/container-host-link.json", body)


SCENARIOS = {
    "container-host-link": Scenario("container-host-link", container_host_link),
    "mininet-isolated": Scenario("mininet-isolated", isolated_mininet_hosts),
    "mininet-connected": Scenario("mininet-connected", connected_mininet_hosts),
    "vm-host-link": Scenario("vm-host-link", vm_host_link),
    "click-policy": Scenario("click-policy", click_policy_vnf),
}


def main():
    os.chdir(CLI_DIR)
    parser = argparse.ArgumentParser(description="Run NIEP integration tests")
    parser.add_argument("scenario", nargs="?", default="all", choices=sorted([*SCENARIOS.keys(), "all"]))
    args = parser.parse_args()

    names = sorted(SCENARIOS) if args.scenario == "all" else [args.scenario]
    failed = False
    for name in names:
        scenario = SCENARIOS[name]
        print("[RUN ] " + scenario.name)
        try:
            scenario.run()
        except Exception as exc:
            failed = True
            print("[FAIL] " + scenario.name + ": " + str(exc))
        else:
            print("[ OK ] " + scenario.name)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
