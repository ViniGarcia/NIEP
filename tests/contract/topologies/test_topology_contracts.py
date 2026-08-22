from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from niep.application.parser import PlatformParser
from niep.application.service import SFCService, TopologyService
from niep.application.executer import Executer
from niep.application.factory import RuntimeFactory
from niep.domain.spec import ContainerSpec
import niep.application.executer as executer_module


def _topology(**overrides):
    value = {
        "ID": "contract",
        "VMS": [],
        "VNFS": [],
        "SFCS": [],
        "CONTAINERS": [],
        "MININET": {"HOSTS": [], "SWITCHES": [], "CONTROLLERS": [], "OVSWITCHES": []},
        "CONNECTIONS": [],
    }
    value.update(overrides)
    return value


def _write(path: Path, value):
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


class _FakeMininetInterface:
    def __init__(self, name):
        self.name = name
        self.mac = None
        self._ip = None

    def setMAC(self, mac):
        self.mac = mac

    def setIP(self, ip):
        self._ip = ip

    def IP(self):
        return self._ip


class _FakeMininetNode:
    def __init__(self, node_id):
        self.name = node_id

    def intf(self, interface):
        return interface

    def cmd(self, _command):
        return ""


class _FakeMininetLink:
    def __init__(self, left, right):
        self.intf1 = _FakeMininetInterface(left.name + "-if")
        self.intf2 = _FakeMininetInterface(right.name + "-if")


class _FakeMininet:
    def __init__(self, **_kwargs):
        self.nodes = {}

    def addHost(self, node_id):
        node = _FakeMininetNode(node_id)
        self.nodes[node_id] = node
        return node

    def addSwitch(self, node_id):
        node = _FakeMininetNode(node_id)
        self.nodes[node_id] = node
        return node

    def addController(self, node_id, **_kwargs):
        node = _FakeMininetNode(node_id)
        self.nodes[node_id] = node
        return node

    def addLink(self, left, right):
        return _FakeMininetLink(left, right)

    def build(self):
        return None


class _FakeCleanup:
    def cleanup(self):
        return None


class _FakeInfrastructure:
    def __init__(self, interfaces=None):
        self.interfaces = interfaces or {}

    def interfaces_mapping(self):
        return self.interfaces

    def start_local_pox(self):
        return object()


def _prepare_with_fake_mininet(path, monkeypatch, *, local_pox=True, interfaces=None):
    monkeypatch.setattr(executer_module, "Mininet", _FakeMininet)
    monkeypatch.setattr(executer_module, "Cleanup", _FakeCleanup)
    monkeypatch.setattr(
        executer_module,
        "Intf",
        lambda name, node=None, mac=None: _FakeMininetInterface(name),
    )
    parser = PlatformParser(path)
    assert parser.STATUS == 0, parser.DETAIL
    configuration = RuntimeFactory().materialize(parser.SPEC)
    executor = Executer(
        configuration,
        infrastructure=_FakeInfrastructure(interfaces),
    )
    # ``topologyUp`` normally registers external runtime endpoints before
    # calling ``mininetPrepare``.  Register them explicitly here so this
    # host-only regression exercises the Mininet boundary in isolation.
    executor.VMS = {item.ID: item for item in configuration.VMS}
    executor.VNFS = {item.ID: item for item in configuration.VNFS}
    executor.CONTAINERS = {item.ID: item for item in configuration.CONTAINERS}
    executor.LOCAL_POX_ENABLED = local_pox
    assert executor.mininetPrepare() == 0, executor.DETAIL
    return parser, executor


def test_tutorial_topologies_remain_valid():
    for path in (
        "tutorial/examples/mininet-ping.json",
        "tutorial/examples/vm-basic.json",
        "tutorial/examples/container-host-link.json",
    ):
        parser = PlatformParser(path)
        assert parser.STATUS == 0, parser.DETAIL
        assert parser.SPEC is not None


def test_relative_nested_paths_are_descriptor_relative(tmp_path, monkeypatch):
    nested = tmp_path / "nested"
    nested.mkdir()
    vm = _write(
        nested / "vm.json",
        {
            "ID": "nested-vm",
            "MEMORY": 1,
            "VCPU": 1,
            "DISK": "tinycore12",
            "MANAGEMENT_MAC": "52:54:00:00:20:01",
            "INTERFACES": [],
        },
    )
    topology = _write(tmp_path / "topology.json", _topology(VMS=["nested/vm.json"]))
    monkeypatch.chdir("/")
    parser = PlatformParser(topology)
    assert parser.STATUS == 0, parser.DETAIL
    assert parser.SPEC.vms[0].path == str(vm.resolve())


def test_invalid_descriptors_accumulate_diagnostics(tmp_path):
    bad = _write(
        tmp_path / "bad.json",
        {"ID": "bad", "IMAGE": 42, "INTERFACES": [{"MAC": "invalid"}]},
    )
    topology = _write(tmp_path / "topology.json", _topology(CONTAINERS=[bad.name], MININET={}))
    parser = PlatformParser(topology)
    assert parser.STATUS == -3
    assert len(parser.RESULT.issues) >= 2
    assert all(issue.file for issue in parser.RESULT.issues)


def test_specs_are_deeply_immutable_and_wire_serializable(tmp_path):
    container = _write(
        tmp_path / "container.json",
        {
            "ID": "immutable",
            "IMAGE": "alpine:latest",
            "SYSCTLS": {"net.ipv4": "1"},
            "INTERFACES": [],
        },
    )
    parser = PlatformParser(_write(tmp_path / "topology.json", _topology(CONTAINERS=[container.name])))
    assert parser.STATUS == 0, parser.DETAIL
    spec = ContainerSpec("nested", str(container), "alpine:latest", ["sleep"],
                         sysctls={"outer": {"inner": [1]}})
    with pytest.raises(TypeError):
        spec.sysctls["new"] = "value"
    with pytest.raises(AttributeError):
        spec.sysctls["outer"]["inner"].append(2)
    json.dumps(spec.to_dict())
    json.dumps(parser.SPEC.to_dict())


def test_duplicate_sfc_ids_and_management_macs_fail_before_factory(tmp_path):
    vm1 = _write(
        tmp_path / "vm1.json",
        {"ID": "vm1", "MEMORY": 1, "VCPU": 1, "DISK": "tinycore12", "MANAGEMENT_MAC": "52:54:00:00:30:01", "INTERFACES": []},
    )
    vm2 = _write(
        tmp_path / "vm2.json",
        {"ID": "vm2", "MEMORY": 1, "VCPU": 1, "DISK": "tinycore12", "MANAGEMENT_MAC": "52:54:00:00:30:01", "INTERFACES": []},
    )
    parser = PlatformParser(_write(tmp_path / "macs.json", _topology(VMS=[vm1.name, vm2.name])))
    assert parser.STATUS == -11
    assert any("management MAC" in issue.message for issue in parser.RESULT.issues)

    for suffix in ("one", "two"):
        vm = _write(
            tmp_path / f"{suffix}-vm.json",
            {"ID": suffix, "MEMORY": 1, "VCPU": 1, "DISK": "tinycore12", "MANAGEMENT_MAC": f"52:54:00:00:31:{suffix == 'two' and '02' or '01'}", "INTERFACES": []},
        )
        _write(tmp_path / f"{suffix}-vnf.json", {"ID": suffix, "VM": vm.name})
        _write(
            tmp_path / f"{suffix}-sfc.json",
            {"ID": "same-sfc", "VNFS": [{"ID": suffix, "PATH": f"{suffix}-vnf.json"}], "IP": {"ID": f"IP-{suffix}", "LINK": f"br-{suffix}"}, "OPS": [{"ID": f"op-{suffix}", "LINK": f"br-op-{suffix}"}], "CONNECTIONS": [{"OLL": f"IP-{suffix}", "ILL": suffix}, {"OLL": suffix, "ILL": f"op-{suffix}"}]},
        )
    parser = PlatformParser(_write(tmp_path / "sfc-topology.json", _topology(SFCS=["one-sfc.json", "two-sfc.json"])))
    assert parser.STATUS == -11
    assert any("SFC" in issue.message for issue in parser.RESULT.issues)


def test_missing_sfc_nested_vnf_uses_legacy_path_code(tmp_path):
    sfc = _write(
        tmp_path / "sfc.json",
        {"ID": "sfc", "VNFS": [{"ID": "x", "PATH": "missing-vnf.json"}], "IP": {"ID": "IP", "LINK": "br0"}, "OPS": [{"ID": "op", "LINK": "br1"}], "CONNECTIONS": [{"OLL": "IP", "ILL": "x"}, {"OLL": "x", "ILL": "op"}]},
    )
    parser = PlatformParser(_write(tmp_path / "topology.json", _topology(SFCS=[sfc.name])))
    assert parser.STATUS == -2
    assert "SFCS[0].VNFS[0].PATH" in parser.DETAIL


def test_sfc_vnf_reference_id_mismatch_accumulates_and_matching_survives_cwd(tmp_path, monkeypatch):
    nested = tmp_path / "nested"
    nested.mkdir()
    _write(
        nested / "vm.json",
        {
            "ID": "real-vnf",
            "MEMORY": 1,
            "VCPU": 1,
            "DISK": "tinycore12",
            "MANAGEMENT_MAC": "52:54:00:00:41:01",
            "INTERFACES": [],
        },
    )
    _write(nested / "vnf.json", {"ID": "real-vnf", "VM": "vm.json"})

    def sfc_document(reference_id, duplicate_operation=False):
        operations = [{"ID": "out", "LINK": "br-out"}]
        if duplicate_operation:
            operations.append({"ID": "out", "LINK": "br-other"})
        return {
            "ID": "chain-" + reference_id,
            "VNFS": [{"ID": reference_id, "PATH": "vnf.json"}],
            "IP": {"ID": "ip", "LINK": "br-in"},
            "OPS": operations,
            "CONNECTIONS": [
                {"OLL": "ip", "ILL": reference_id, "ILL_MAC": "52:54:00:41:00:01"},
                {"OLL": reference_id, "ILL": "out", "OLL_MAC": "52:54:00:41:00:02"},
            ],
        }

    mismatch = _write(
        nested / "mismatch.json",
        sfc_document("alias-vnf", duplicate_operation=True),
    )
    mismatch_topology = _write(
        tmp_path / "mismatch-topology.json",
        _topology(SFCS=["nested/mismatch.json"]),
    )
    monkeypatch.chdir(tmp_path.parent)
    parser = PlatformParser(mismatch_topology)
    assert parser.STATUS == -5
    assert len(parser.RESULT.issues) >= 2
    mismatch_issues = [
        issue for issue in parser.RESULT.issues
        if "reference ID does not match" in issue.message
    ]
    assert mismatch_issues
    assert mismatch_issues[0].field == "SFCS[0].VNFS[0].ID"
    assert mismatch_issues[0].file == str((nested / "vnf.json").resolve())
    assert mismatch_issues[0].value == {"reference": "alias-vnf", "descriptor": "real-vnf"}

    matching = _write(nested / "matching.json", sfc_document("real-vnf"))
    matching_topology = _write(
        tmp_path / "matching-topology.json",
        _topology(SFCS=["nested/matching.json"]),
    )
    matching_parser = PlatformParser(matching_topology)
    assert matching_parser.STATUS == 0, matching_parser.DETAIL
    assert matching_parser.SPEC.sfcs[0].vnfs[0]["ID"] == "real-vnf"


def test_service_materializes_mutable_runtime_configuration_without_mutating_spec():
    class FakeExecutor:
        STATUS = None

        def __init__(self, configuration):
            self.CONFIGURATION = configuration

    service = TopologyService(executor_factory=FakeExecutor)
    result = service.define("tutorial/examples/mininet-ping.json")
    assert result.ok
    assert result.data.CONFIGURATION.MNHOSTS[0].ELEM is None
    result.data.CONFIGURATION.MNHOSTS[0].ELEM = object()
    assert result.data.CONFIGURATION.SPEC.mininet_hosts[0].ELEM is None


def test_executor_materializes_mutable_mininet_nodes_for_connected_ovs_and_click(
    tmp_path, monkeypatch
):
    connected_parser, connected = _prepare_with_fake_mininet(
        "tests/topologies/mininet-connected-hosts.json", monkeypatch
    )
    assert connected.SWITCHES["s1"].ELEM is not None
    assert connected.CONTROLLERS["UNICTRL"].ELEM is not None
    assert connected_parser.SPEC.mininet_switches[0].ELEM is None

    controller_topology = _write(
        tmp_path / "controller-ovs.json",
        _topology(
            MININET={
                "HOSTS": [],
                "SWITCHES": [],
                "CONTROLLERS": [{"ID": "c1", "IP": "127.0.0.1", "PORT": 6633}],
                "OVSWITCHES": [{"ID": "ovs1", "CONTROLLER": "c1"}],
            }
        ),
    )
    _parser, configured = _prepare_with_fake_mininet(
        controller_topology, monkeypatch, local_pox=False
    )
    assert configured.CONTROLLERS["c1"].ELEM is not None
    assert configured.OVSSWITCHES["ovs1"].ELEM is not None

    click_parser, click = _prepare_with_fake_mininet(
        "tests/topologies/click-policy-vnf.json",
        monkeypatch,
        interfaces={"br-click0": "br-click0", "br-click1": "br-click1"},
    )
    assert click.SWITCHES["s1"].ELEM is not None
    assert click.CONTROLLERS["UNICTRL"].ELEM is not None
    assert click_parser.SPEC.mininet_hosts[0].ELEM is None


def test_parser_import_is_free_of_optional_infrastructure(tmp_path):
    code = """
import importlib, sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.', 1)[0] in {'docker', 'libvirt', 'mininet'}:
            raise AssertionError(fullname)
        return None
sys.meta_path.append(Block())
importlib.import_module('niep.application.parser')
assert not any(name.split('.', 1)[0] in {'docker', 'libvirt', 'mininet'} for name in sys.modules)
"""
    child_env = os.environ.copy()
    for key in ("COV_CORE_SOURCE", "COV_CORE_CONFIG", "COV_CORE_DATAFILE"):
        child_env.pop(key, None)
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        env=child_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_sfc_materialization_is_absolute_and_lifecycle_uses_bound_vnfs(tmp_path, monkeypatch):
    nested = tmp_path / "nested"
    nested.mkdir()
    vm_path = _write(
        nested / "vm.json",
        {
            "ID": "vnf-a",
            "MEMORY": 1,
            "VCPU": 1,
            "DISK": "tinycore12",
            "MANAGEMENT_MAC": "52:54:00:00:40:01",
            "INTERFACES": [],
        },
    )
    vnf_path = _write(nested / "vnf.json", {"ID": "vnf-a", "VM": vm_path.name})
    sfc_path = _write(
        nested / "chain.json",
        {
            "ID": "chain",
            "VNFS": [{"ID": "vnf-a", "PATH": vnf_path.name}],
            "IP": {"ID": "ip", "LINK": "br-in"},
            "OPS": [{"ID": "out", "LINK": "br-out"}],
            "CONNECTIONS": [
                {"OLL": "ip", "ILL": "vnf-a", "ILL_MAC": "52:54:00:40:00:01"},
                {"OLL": "vnf-a", "ILL": "out", "OLL_MAC": "52:54:00:40:00:02"},
            ],
        },
    )
    topology_path = _write(
        tmp_path / "topology.json",
        _topology(SFCS=["nested/chain.json"]),
    )

    class FakeVNF:
        def __init__(self, path, _interfaces=None):
            self.VNF_JSON = path
            self.ID = json.loads(Path(path).read_text(encoding="utf-8"))["ID"]
            self.VNF_STATUS = 0
            self.VNF_UP = False
            self.calls = []

        def createVNF(self):
            self.calls.append("create")
            return 0

        def upVNF(self):
            self.calls.append("up")
            if self.VNF_UP:
                return -1
            self.VNF_UP = True
            return 0

        def downVNF(self):
            self.calls.append("down")
            if not self.VNF_UP:
                return -1
            self.VNF_UP = False
            return 0

    class FakeExecutor:
        STATUS = None

        def __init__(self, configuration):
            self.CONFIGURATION = configuration
            self.VMS = {}
            self.VNFS = {}
            self.CONTAINERS = {}

    monkeypatch.chdir(tmp_path.parent)
    factory = RuntimeFactory(runtime_types={"VNF": FakeVNF})
    service = TopologyService(runtime_factory=factory, executor_factory=FakeExecutor)
    result = service.define(str(topology_path))
    assert result.ok, result.detail

    service.executor.STATUS = 0
    sfc = service.executor.CONFIGURATION.SFCS[0]
    assert sfc.SFC_JSON == str(sfc_path.resolve())
    assert sfc.SFC_VNFS_CONF
    assert sfc.SFC_VNFS_CONF[0][0] == ("vnf-a", str(vnf_path.resolve()))
    assert [instance.ID for instance in sfc.SFC_VNF_INSTANCES] == ["vnf-a"]
    assert sfc.SFC_VNF_INSTANCES[0] is service.executor.CONFIGURATION.VNFS[0]
    bound_instance = sfc.SFC_VNF_INSTANCES[0]
    assert all(Path(conf[0][1]).is_absolute() for conf in sfc.SFC_VNFS_CONF)

    sfc_service = SFCService(service)
    started = sfc_service.up("chain")
    assert started.ok
    assert sfc.SFC_UP
    assert sfc.SFC_VNF_INSTANCES[0].calls == ["create", "up"]

    stopped = sfc_service.down("chain")
    assert stopped.ok
    assert not sfc.SFC_UP
    assert sfc.SFC_VNF_INSTANCES == []
    assert sfc.SFC_LAST_INSTANCES[0] is bound_instance
    assert bound_instance.calls == ["create", "up", "down"]

    restarted = sfc_service.up("chain")
    assert restarted.ok
    assert sfc.SFC_VNF_INSTANCES[0] is bound_instance
