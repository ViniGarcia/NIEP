"""Collectable wrappers around teardown characterization checks."""

from __future__ import annotations

import pytest

from tests import check_teardown


pytestmark = pytest.mark.contract


def test_teardown_characterization_suite() -> None:
    """Reuse every host-safe assertion from the legacy executable script."""

    check_teardown.check_each_stage_is_best_effort()
    check_teardown.check_multiple_failures_are_aggregated()
    check_teardown.check_numeric_cleanup_status_is_a_failure()
    check_teardown.check_legacy_cleanup_errors_are_not_split_or_dropped()
    check_teardown.check_retry_only_repeats_pending_cleanup()
    check_teardown.check_rollback_uses_the_teardown_plan()
    check_teardown.check_down_and_clean_preserve_executor_on_failure()
    check_teardown.check_dispatcher_propagates_cleanup_failure()
    check_teardown.check_destroy_gates_persistent_state_on_teardown()
    check_teardown.check_destroy_reports_persistent_state_failures()
    check_teardown.check_failed_start_preserves_executor_only_when_needed()
    check_teardown.check_container_cleanup_is_best_effort_per_interface()
    check_teardown.check_container_cleanup_retry_skips_completed_interfaces()
    check_teardown.check_vm_cleanup_attempts_domain_and_all_interfaces()
    check_teardown.check_vm_cleanup_retry_skips_completed_domain_operation()
    check_teardown.check_vnf_cleanup_normalizes_legacy_errors()
    check_teardown.check_global_infrastructure_aggregates_subresource_failures()
    check_teardown.check_global_infrastructure_retry_skips_completed_resource()
