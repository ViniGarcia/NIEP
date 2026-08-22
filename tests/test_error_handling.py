"""Collectable wrappers for host-safe error and rollback checks."""

from __future__ import annotations

import importlib
import json

import pytest

from tests import check_error_handling
from niep.paths import NIEPPathError


pytestmark = pytest.mark.contract


def test_parser_diagnostics(tmp_path) -> None:
    check_error_handling.check_parser_diagnostics(tmp_path)


def test_parser_reports_runtime_asset_path_error_without_traceback(tmp_path, monkeypatch) -> None:
    """VM materialization failures remain structured parser diagnostics."""

    descriptor = tmp_path / "vm.json"
    descriptor.write_text("{}", encoding="utf-8")
    topology = tmp_path / "topology.json"
    topology.write_text(
        json.dumps(
            {
                "ID": "missing-runtime-asset",
                "VMS": [descriptor.name],
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
        ),
        encoding="utf-8",
    )

    parser_module = importlib.import_module("niep.application.parser")

    def fail_to_materialize(*args, **kwargs):
        raise NIEPPathError("asset VEM/IMAGES is unavailable")

    monkeypatch.setattr(parser_module, "VM", fail_to_materialize)
    parser = parser_module.PlatformParser(str(topology))

    assert parser.STATUS == -3
    assert parser.ERROR == {
        "message": "NIEP runtime asset unavailable: asset VEM/IMAGES is unavailable",
        "field": "VMS[0]",
        "value": None,
        "file": str(descriptor),
    }
    assert "NIEP runtime asset unavailable" in parser.DETAIL


def test_docker_runtime_start_error_is_structured() -> None:
    check_error_handling.check_docker_runtime_start_error()


def test_container_exec_error_is_structured() -> None:
    check_error_handling.check_container_exec_error_result()


def test_container_network_failure_rolls_back(tmp_path) -> None:
    check_error_handling.check_container_network_rollback(tmp_path)


@pytest.mark.integration
@pytest.mark.privileged
def test_failed_topology_start_cleanup_requires_infrastructure(tmp_path) -> None:
    check_error_handling.check_failed_topology_start_cleanup(tmp_path)
