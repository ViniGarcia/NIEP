#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from tests.support import install_optional_dependency_stubs

install_optional_dependency_stubs()
sys.path.insert(0, str(ROOT / "TOPO-MAN"))
sys.path.insert(0, str(ROOT / "VEM"))

from Container import Container  # noqa: E402
from ContainerNetworkRuntime import ContainerNetworkError  # noqa: E402
from Command import CommandDispatcher  # noqa: E402
from DockerRuntime import DockerRuntime, DockerRuntimeError  # noqa: E402
from Parser import PlatformParser  # noqa: E402
from Service import ContainerService  # noqa: E402


def base_topology():
    return {
        "ID": "ErrorTest",
        "VMS": [],
        "VNFS": [],
        "SFCS": [],
        "CONTAINERS": [],
        "MININET": {
            "HOSTS": [],
            "SWITCHES": [],
            "CONTROLLERS": [],
            "OVSWITCHES": [],
        },
        "CONNECTIONS": [],
    }


def write_json(directory, name, data):
    path = directory / name
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def assert_parser_error(path, status, detail_parts):
    parser = PlatformParser(str(path))
    if parser.STATUS != status:
        raise AssertionError("unexpected parser status: " + repr(parser.STATUS) + " detail=" + parser.DETAIL)
    for part in detail_parts:
        if part not in parser.DETAIL:
            raise AssertionError("missing " + repr(part) + " in " + repr(parser.DETAIL))


def check_parser_diagnostics(directory):
    malformed = directory / "malformed.json"
    malformed.write_text('{"ID": "broken",', encoding="utf-8")
    assert_parser_error(malformed, -1, ["Invalid JSON syntax", "line 1", "column"])

    missing = base_topology()
    del missing["CONNECTIONS"]
    assert_parser_error(write_json(directory, "missing.json", missing), -1, ["Missing required key", "field=CONNECTIONS"])

    invalid_mac = base_topology()
    invalid_mac["MININET"]["HOSTS"] = [
        {"ID": "h1", "INTERFACES": [{"MAC": "not-a-mac", "IP": "10.0.0.1/24"}]}
    ]
    assert_parser_error(
        write_json(directory, "invalid-mac.json", invalid_mac),
        -7,
        ["Invalid MAC address", "MININET.HOSTS[0].INTERFACES[0].MAC", "not-a-mac"],
    )

    unknown_endpoint = base_topology()
    unknown_endpoint["MININET"]["SWITCHES"] = ["s1"]
    unknown_endpoint["CONNECTIONS"] = [{"IN/OUT": "missing", "OUT/IN": "s1"}]
    assert_parser_error(
        write_json(directory, "unknown-endpoint.json", unknown_endpoint),
        -12,
        ["unknown endpoint", "CONNECTIONS[0].IN/OUT", "missing"],
    )

    invalid_container = {
        "ID": "bad-container",
        "IMAGE": 42,
        "INTERFACES": [],
    }
    write_json(directory, "invalid-container.json", invalid_container)
    container_topology = base_topology()
    container_topology["CONTAINERS"] = ["invalid-container.json"]
    assert_parser_error(
        write_json(directory, "invalid-container-topology.json", container_topology),
        -3,
        ["IMAGE must be a non-empty string", "field=CONTAINERS[0]"],
    )

    invalid_container_ip = {
        "ID": "bad-container-ip",
        "IMAGE": "alpine:3.20",
        "INTERFACES": [
            {
                "ID": "ct-badip0",
                "MAC": "02:00:00:00:91:01",
                "IP": "10.0.999.1/24",
            }
        ],
    }
    write_json(directory, "invalid-container-ip.json", invalid_container_ip)
    container_ip_topology = base_topology()
    container_ip_topology["CONTAINERS"] = ["invalid-container-ip.json"]
    assert_parser_error(
        write_json(directory, "invalid-container-ip-topology.json", container_ip_topology),
        -3,
        ["IP is not a valid IP address with prefix", "10.0.999.1/24"],
    )

    invalid_sysctls = {
        "ID": "bad-container-sysctls",
        "IMAGE": "alpine:3.20",
        "SYSCTLS": ["net.ipv4.ip_forward=1"],
        "INTERFACES": [],
    }
    write_json(directory, "invalid-container-sysctls.json", invalid_sysctls)
    sysctls_topology = base_topology()
    sysctls_topology["CONTAINERS"] = ["invalid-container-sysctls.json"]
    assert_parser_error(
        write_json(directory, "invalid-container-sysctls-topology.json", sysctls_topology),
        -3,
        ["SYSCTLS must be a JSON object", "field=CONTAINERS[0]"],
    )

    duplicate_id = base_topology()
    duplicate_id["MININET"]["HOSTS"] = [
        {"ID": "node1", "INTERFACES": [{"MAC": "02:00:00:00:92:01", "IP": "10.92.0.1/24"}]}
    ]
    duplicate_id["MININET"]["SWITCHES"] = ["node1"]
    assert_parser_error(
        write_json(directory, "duplicate-id.json", duplicate_id),
        -8,
        ["Duplicate topology node ID", "node1"],
    )

    reused_interface = base_topology()
    reused_interface["MININET"]["HOSTS"] = [
        {"ID": "h1", "INTERFACES": [{"MAC": "02:00:00:00:94:01", "IP": "10.94.0.1/24"}]}
    ]
    reused_interface["MININET"]["SWITCHES"] = ["s1", "s2"]
    reused_interface["CONNECTIONS"] = [
        {
            "IN/OUT": "h1",
            "IN/OUTIFACE": "02:00:00:00:94:01",
            "OUT/IN": "s1",
        },
        {
            "IN/OUT": "h1",
            "IN/OUTIFACE": "02:00:00:00:94:01",
            "OUT/IN": "s2",
        },
    ]
    assert_parser_error(
        write_json(directory, "reused-interface.json", reused_interface),
        -11,
        ["used by more than one connection", "CONNECTIONS[1].IN/OUTIFACE"],
    )


class FakeContainer:
    def __init__(self):
        self.name = "test-container"
        self.status = "created"
        self.attrs = {"State": {"ExitCode": 17, "Pid": 0}}

    def start(self):
        self.status = "exited"

    def reload(self):
        return None

    def logs(self, tail=None):
        return b"invalid startup command"


class FakeRuntime:
    def __init__(self):
        self.container = FakeContainer()
        self.removals = []

    def remove(self, container_id):
        self.removals.append(container_id)

    def exists(self, container_id):
        return False

    def create(self, container_id, image, command, privileged, entrypoint, sysctls):
        return self.container

    def lookup(self, container_id):
        return self.container

    def start(self, container):
        container.status = "running"
        container.attrs["State"]["Pid"] = 123
        return container


class FailingNetwork:
    def __init__(self):
        self.released = False

    def setup_interfaces(self, container, interfaces):
        raise ContainerNetworkError("create_veth", interfaces[0]["ID"], ["ip", "link", "add"], "device exists")

    def release_interfaces(self, interfaces):
        self.released = True


class FailingExecContainer:
    def execContainer(self, command):
        raise DockerRuntimeError("exec", "Docker container is not running", container_id="stopped-container")


class FakeTopologyService:
    def get_container(self, container_id):
        return FailingExecContainer()


def check_docker_runtime_start_error():
    try:
        DockerRuntime().start(FakeContainer())
    except DockerRuntimeError as exc:
        message = str(exc)
        if "exit code 17" not in message or "invalid startup command" not in message:
            raise AssertionError(message)
    else:
        raise AssertionError("DockerRuntime.start accepted an exited container")


def check_container_exec_error_result():
    result = ContainerService(FakeTopologyService()).exec("stopped-container", "true")
    if result.ok or result.code.value != "container_runtime_error":
        raise AssertionError(result.to_dict())
    if "not running" not in result.detail or "stopped-container" not in result.detail:
        raise AssertionError(result.to_dict())


def check_container_network_rollback(directory):
    descriptor = {
        "ID": "rollback-test",
        "IMAGE": "example:local",
        "COMMAND": ["sleep", "infinity"],
        "INTERFACES": [
            {
                "ID": "ct-roll0",
                "MAC": "02:00:00:00:90:01",
                "IP": "10.90.0.1/24",
            }
        ],
    }
    container = Container(str(write_json(directory, "rollback-container.json", descriptor)))
    runtime = FakeRuntime()
    network = FailingNetwork()
    container.RUNTIME = runtime
    container.NETWORK = network

    result = container.upContainer()
    if result != -10:
        raise AssertionError("unexpected container status: " + repr(result))
    if container.CONTAINER is not None:
        raise AssertionError("failed container was not cleared")
    if not network.released:
        raise AssertionError("container interfaces were not released")
    if runtime.removals.count("rollback-test") < 2:
        raise AssertionError("container was not removed during rollback")
    if "create_veth" not in container.DETAIL or "device exists" not in container.DETAIL:
        raise AssertionError(container.DETAIL)


def command_succeeds(command):
    return subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def check_failed_topology_start_cleanup(directory):
    descriptor = {
        "ID": "invalid-image-test",
        "IMAGE": "invalid image reference",
        "COMMAND": ["sleep", "infinity"],
        "INTERFACES": [
            {
                "ID": "ct-invalid0",
                "MAC": "02:00:00:00:93:01",
                "IP": "10.93.0.1/24",
            }
        ],
    }
    write_json(directory, "invalid-image-container.json", descriptor)
    topology = base_topology()
    topology["CONTAINERS"] = ["invalid-image-container.json"]
    topology_path = write_json(directory, "invalid-image-topology.json", topology)

    dispatcher = CommandDispatcher()
    define = dispatcher.dispatch("define", [str(topology_path)])
    if not define.ok:
        raise AssertionError(define.to_dict())
    result = dispatcher.dispatch("topoup")
    if result.ok or result.code.value != "topology_up_failed":
        raise AssertionError(result.to_dict())
    if "invalid-image-test" not in result.detail or "invalid image reference" not in result.detail:
        raise AssertionError(result.to_dict())
    if command_succeeds(["docker", "inspect", "invalid-image-test"]):
        raise AssertionError("failed container was left behind")
    if command_succeeds(["ip", "link", "show", "ct-invalid0"]):
        raise AssertionError("failed container interface was left behind")
    if command_succeeds(["ip", "link", "show", "vbrNIEP"]):
        raise AssertionError("global NIEP bridge was left behind after failed startup")


def main():
    with tempfile.TemporaryDirectory(prefix="niep-errors-") as temp:
        directory = Path(temp)
        check_parser_diagnostics(directory)
        check_docker_runtime_start_error()
        check_container_exec_error_result()
        check_container_network_rollback(directory)
        check_failed_topology_start_cleanup(directory)
    print("[ OK ] parser and Docker runtime error handling")


if __name__ == "__main__":
    main()
