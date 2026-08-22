"""Collectable wrappers for host-safe error and rollback checks."""

from __future__ import annotations

import pytest

from tests import check_error_handling


pytestmark = pytest.mark.contract


def test_parser_diagnostics(tmp_path) -> None:
    check_error_handling.check_parser_diagnostics(tmp_path)


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
