#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import shlex
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


def container_exec(dispatcher, container_id, command, code=0):
    result = dispatch(dispatcher, "container", ["exec", container_id, *shlex.split(command)], code="container_exec")
    if result.data["exit_code"] != code:
        raise TestFailure(str(result.to_dict()))
    return result.data["output"]


def parse_receiver_bitrate(output):
    matches = re.findall(r"([0-9.]+)\s+([KMG])bits/sec.*receiver", output)
    if not matches:
        raise TestFailure("could not parse receiver bitrate:\n" + output)
    value, unit = matches[-1]
    multiplier = {"K": 0.001, "M": 1.0, "G": 1000.0}[unit]
    return float(value) * multiplier


def parse_receiver_loss(output):
    matches = re.findall(r"\(([0-9.]+)%\)\s+receiver", output)
    if not matches:
        raise TestFailure("could not parse receiver loss:\n" + output)
    return float(matches[-1])


def wait_for_vm_management(dispatcher, vm_id, attempts=12):
    for _ in range(attempts):
        result = dispatcher.dispatch("vm", ["management", vm_id])
        if result.ok:
            return result.data
        time.sleep(2)
    raise TestFailure("VM management address not available: " + str(result.to_dict()))


def ssh_vm(ip_address, command, attempts=10):
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
    for attempt in range(attempts):
        completed = subprocess.run(
            ssh_command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
        )
        if completed.returncode == 0:
            return completed.stdout
        if attempt + 1 < attempts and (
            "Connection refused" in completed.stdout
            or "Connection timed out" in completed.stdout
            or "No route to host" in completed.stdout
        ):
            time.sleep(2)
            continue
        raise TestFailure(completed.stdout)
    raise TestFailure("SSH did not become ready at " + ip_address)


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

        container_ip = container_exec(dispatcher, "test-alpine", "ip -o addr show eth0")
        assert_contains(container_ip, "10.50.0.2/24")

        if not mininet_probe(dispatcher, "h1", "ping -c1 -W2 10.50.0.2"):
            raise TestFailure("h1 did not reach container interface")

        container_exec(dispatcher, "test-alpine", "ping -c1 -W2 10.50.0.1")

    run_topology("../tests/topologies/container-host-link.json", body)


def container_router():
    dispatcher = CommandDispatcher()
    try:
        dispatch(dispatcher, "define", ["../tests/topologies/container-router.json"], code="defined")
        dispatch(dispatcher, "topoup", code="topology_up")

        container_list = dispatch(dispatcher, "container", ["list"], code="defined")
        if container_list.data != ["test-alpine-router"]:
            raise TestFailure(str(container_list.to_dict()))

        eth0 = container_exec(dispatcher, "test-alpine-router", "ip -o addr show eth0")
        eth1 = container_exec(dispatcher, "test-alpine-router", "ip -o addr show eth1")
        eth0_link = container_exec(dispatcher, "test-alpine-router", "ip -o link show eth0")
        eth1_link = container_exec(dispatcher, "test-alpine-router", "ip -o link show eth1")
        assert_contains(eth0, "10.100.0.1/24")
        assert_contains(eth1, "10.101.0.1/24")
        assert_contains(eth0_link.lower(), "02:00:00:01:00:01")
        assert_contains(eth1_link.lower(), "02:00:00:01:01:01")

        forwarding = container_exec(dispatcher, "test-alpine-router", "cat /proc/sys/net/ipv4/ip_forward")
        if forwarding.strip() != "1":
            raise TestFailure("IPv4 forwarding is disabled: " + repr(forwarding))

        if not mininet_probe(dispatcher, "h1", "ping -c1 -W2 10.100.0.1"):
            raise TestFailure("h1 did not reach router eth0")
        if not mininet_probe(dispatcher, "h2", "ping -c1 -W2 10.101.0.1"):
            raise TestFailure("h2 did not reach router eth1")

        mininet_cmd(dispatcher, "h1", "ip route add 10.101.0.0/24 via 10.100.0.1")
        mininet_cmd(dispatcher, "h2", "ip route add 10.100.0.0/24 via 10.101.0.1")

        if not mininet_probe(dispatcher, "h1", "ping -c2 -W2 10.101.0.2"):
            raise TestFailure("h1 did not reach h2 through the container router")
        if not mininet_probe(dispatcher, "h2", "ping -c2 -W2 10.100.0.2"):
            raise TestFailure("h2 did not reach h1 through the container router")
    finally:
        down = dispatcher.dispatch("topodown")
        if not down.ok and down.code.value != "no_topology":
            raise TestFailure("topology cleanup failed: " + str(down.to_dict()))

    for command, resource in (
        (["docker", "inspect", "test-alpine-router"], "container"),
        (["ip", "link", "show", "ct-rtr0"], "ct-rtr0"),
        (["ip", "link", "show", "ct-rtr1"], "ct-rtr1"),
    ):
        completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if completed.returncode == 0:
            raise TestFailure(resource + " was left behind after topodown")


def iperf_click_shaper():
    def body(dispatcher):
        container_list = dispatch(dispatcher, "container", ["list"], code="defined")
        if sorted(container_list.data) != ["test-iperf-client", "test-iperf-server"]:
            raise TestFailure(str(container_list.to_dict()))

        dispatch(
            dispatcher,
            "vnf",
            ["action", "test-click-shaper", "POST_FUNCTION", "../tests/fixtures/click/udp-shaper.click"],
            code="vnf_action",
        )
        dispatch(dispatcher, "vnf", ["action", "test-click-shaper", "POST_START"], code="vnf_action")
        time.sleep(2)

        client_ip = container_exec(dispatcher, "test-iperf-client", "ip -o addr show eth0")
        server_ip = container_exec(dispatcher, "test-iperf-server", "ip -o addr show eth0")
        assert_contains(client_ip, "10.80.0.1/24")
        assert_contains(server_ip, "10.80.0.2/24")
        container_exec(dispatcher, "test-iperf-client", "ping -c1 -W2 10.80.0.2")

        tcp_output = container_exec(dispatcher, "test-iperf-client", "iperf3 -c 10.80.0.2 -t 3")
        tcp_receiver = parse_receiver_bitrate(tcp_output)
        if tcp_receiver < 100.0:
            raise TestFailure("TCP receiver bitrate too low: " + str(tcp_receiver) + " Mbits/sec\n" + tcp_output)

        udp_output = container_exec(dispatcher, "test-iperf-client", "iperf3 -u -b 20M -c 10.80.0.2 -t 5")
        udp_receiver = parse_receiver_bitrate(udp_output)
        udp_loss = parse_receiver_loss(udp_output)
        if udp_receiver >= 10.0:
            raise TestFailure("UDP receiver bitrate was not policed: " + str(udp_receiver) + " Mbits/sec\n" + udp_output)
        if udp_loss < 30.0:
            raise TestFailure("UDP loss too low for policer: " + str(udp_loss) + "%\n" + udp_output)

    run_topology("../tests/topologies/iperf-click-shaper.json", body)


SCENARIOS = {
    "container-host-link": Scenario("container-host-link", container_host_link),
    "container-router": Scenario("container-router", container_router),
    "mininet-isolated": Scenario("mininet-isolated", isolated_mininet_hosts),
    "mininet-connected": Scenario("mininet-connected", connected_mininet_hosts),
    "vm-host-link": Scenario("vm-host-link", vm_host_link),
    "click-policy": Scenario("click-policy", click_policy_vnf),
}

HEAVY_SCENARIOS = {
    "iperf-click-shaper": Scenario("iperf-click-shaper", iperf_click_shaper),
}


def main():
    os.chdir(CLI_DIR)
    parser = argparse.ArgumentParser(description="Run NIEP integration tests")
    parser.add_argument("scenario", nargs="?", default="all", choices=sorted([*SCENARIOS.keys(), *HEAVY_SCENARIOS.keys(), "all", "heavy"]))
    args = parser.parse_args()

    if args.scenario == "all":
        selected = SCENARIOS
        names = sorted(selected)
    elif args.scenario == "heavy":
        selected = HEAVY_SCENARIOS
        names = sorted(selected)
    elif args.scenario in HEAVY_SCENARIOS:
        selected = HEAVY_SCENARIOS
        names = [args.scenario]
    else:
        selected = SCENARIOS
        names = [args.scenario]

    failed = False
    for name in names:
        scenario = selected[name]
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
