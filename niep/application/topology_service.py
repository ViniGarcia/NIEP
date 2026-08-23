"""Topology lifecycle use case backed by an explicit executor port."""

from __future__ import annotations

from os.path import join
import warnings

from niep.application.executer import Executer
from niep.application.executor_port import ExecutorTopologyPort, LegacyExecutorAdapter
from niep.application.factory import RuntimeFactory
from niep.application.lifecycle import TopologyState, TopologyStateMachine
from niep.application.parser import PlatformParser
from niep.domain.result import ResultCode, ServiceResult
from niep.paths import asset_directory
from niep.runtime.errors import cleanup_failure_record


PARSERERRORS = {
    -1: "Invalid definition file path or invalid key included",
    -2: "Invalid data type included as a key value",
    -3: "Invalid VM, VNF, or container configuration provided",
    -4: "Invalid SFC file path provided",
    -5: "Invalid SFC configuration provided",
    -6: "Invalid Mininet configuration provided",
    -7: "Invalid Mininet host configuration provided",
    -8: "Invalid Mininet switch configuration provided",
    -9: "Invalid Mininet controller configuration provided",
    -10: "Invalid Mininet OVS switch configuration provided",
    -11: "Invalid connections configuration provided",
    -12: "Invalid In/Out point configuration provided",
    -13: "Invalid Out/In point configuration provided",
    -14: "Inconsistent In/Out and Out/In points",
}

EXECUTERERRORS = {
    -1: "Mininet network interfaces mapping failed",
    -2: "Invalid definition of Mininet network interface",
    -3: "Unrecognized Mininet network interface",
    -4: "Parser error detected",
}


class TopologyService:
    """Lifecycle service using only typed operations from its executor port.

    ``executor`` is retained as a deprecated compatibility property for old
    in-process tests/callers. It delegates to the port and is not used by the
    lifecycle implementation or command handlers.
    """

    def __init__(
        self,
        runtime_factory=None,
        executor_factory=None,
        parser_factory=None,
        topology_port: ExecutorTopologyPort | None = None,
    ):
        self._port = topology_port or LegacyExecutorAdapter()
        self._lifecycle = TopologyStateMachine(TopologyState.UNDEFINED)
        self.runtime_factory = runtime_factory if runtime_factory is not None else RuntimeFactory()
        self.executor_factory = executor_factory if executor_factory is not None else Executer
        self.parser_factory = parser_factory if parser_factory is not None else PlatformParser

    @property
    def executor(self):
        """Deprecated raw-executor shim; use snapshots and lifecycle methods."""
        warnings.warn(
            "TopologyService.executor is deprecated; use typed topology ports; "
            "removal planned for NIEP 1.3.0",
            DeprecationWarning,
            stacklevel=2,
        )
        compatibility = getattr(self._port, "compatibility_executor", None)
        return compatibility() if callable(compatibility) else None

    @executor.setter
    def executor(self, value):
        warnings.warn(
            "TopologyService.executor is deprecated; use typed topology ports; "
            "removal planned for NIEP 1.3.0",
            DeprecationWarning,
            stacklevel=2,
        )
        if value is None:
            self._port.detach()
            return
        self._port.attach(value)
        self._reconcile_attached()

    def _reconcile_attached(self):
        runtime_state = self._port.snapshot().lifecycle_state
        if runtime_state is None:
            self._lifecycle.force(TopologyState.DEFINED)
        elif self.state == runtime_state:
            return
        elif self._lifecycle.can_transition(runtime_state):
            self._lifecycle.transition(runtime_state)
        else:
            self._lifecycle.force(runtime_state)

    @property
    def state(self):
        return self._lifecycle.state

    @property
    def lifecycle_state(self):
        return self._lifecycle.state

    def is_defined(self) -> bool:
        return self._port.snapshot().attached

    def _transition(self, target, *, force=False):
        target = TopologyState(target)
        if force:
            return self._lifecycle.force(target)
        if self.state == target:
            return target
        return self._lifecycle.transition(target)

    def _sync_runtime_state(self, result=None):
        snapshot = self._port.snapshot()
        runtime_state = snapshot.lifecycle_state
        if runtime_state is not None:
            if self.state == runtime_state:
                return self.state
            if self._lifecycle.can_transition(runtime_state):
                self._transition(runtime_state)
            else:
                self._transition(runtime_state, force=True)
            return self.state
        # Very old executor doubles expose neither typed lifecycle nor STATUS;
        # in that compatibility shape the operation return value is the only
        # status signal (the historical service used the same fallback).
        status_present = getattr(snapshot, "status_present", snapshot.status is not None)
        status = snapshot.status if status_present else result
        successful = isinstance(status, int) and not isinstance(status, bool) and status == 0
        self._transition(TopologyState.UP if successful else TopologyState.FAILED, force=True)
        return self.state

    def define(self, definition_path):
        snapshot = self._port.snapshot()
        replace_executor = False
        if snapshot.attached:
            state = snapshot.lifecycle_state or self.state
            if state == TopologyState.DOWN:
                replace_executor = True
            elif state == TopologyState.DEFINED:
                replace_executor = (
                    not snapshot.cleanup_required
                    and not snapshot.cleanup_errors
                    and not snapshot.active_resources
                    and not snapshot.journal_incomplete
                )
            if not replace_executor:
                return ServiceResult(
                    ok=False,
                    code=ResultCode.ALREADY_EXECUTED,
                    message="TOPOLOGY MUST BE CLEANED BEFORE REDEFINITION",
                )
        try:
            parser = self.parser_factory(definition_path)
        except Exception as exc:
            return ServiceResult(
                ok=False,
                code=ResultCode.PARSER_ERROR,
                message="Unexpected error while reading topology definition",
                detail=str(exc),
            )
        if parser.STATUS != 0:
            detail = getattr(parser, "DETAIL", "")
            return ServiceResult(
                ok=False,
                code=ResultCode.PARSER_ERROR,
                message=PARSERERRORS.get(parser.STATUS, "Parser error"),
                data=parser,
                status=parser.STATUS,
                detail=detail,
            )
        try:
            materialize = getattr(self.runtime_factory, "materialize", None)
            if materialize is None:
                materialize = getattr(self.runtime_factory, "build", None)
            if materialize is None:
                raise TypeError("runtime factory does not provide materialize()")
            configuration = materialize(parser.SPEC)
            candidate = self.executor_factory(configuration)
        except Exception as exc:
            detail = "Runtime materialization failed: " + str(exc)
            parser.fail(-3, detail, file=getattr(parser, "SOURCE", definition_path))
            return ServiceResult(
                ok=False,
                code=ResultCode.PARSER_ERROR,
                message=PARSERERRORS[-3],
                data=parser,
                status=-3,
                detail=detail,
            )

        candidate_port = LegacyExecutorAdapter(candidate)
        candidate_snapshot = candidate_port.snapshot()
        if candidate_snapshot.status is not None:
            return ServiceResult(
                ok=False,
                code=ResultCode.EXECUTER_ERROR,
                message=EXECUTERERRORS.get(candidate_snapshot.status, "Executer error"),
                data=candidate,
                status=candidate_snapshot.status,
            )
        if replace_executor:
            self._port.detach()
            if self.state != TopologyState.UNDEFINED:
                self._transition(TopologyState.UNDEFINED)
            self._port.attach(candidate)
        else:
            self._port.attach(candidate)
        self._reconcile_attached()
        return ServiceResult(ok=True, code=ResultCode.DEFINED, data=candidate)

    def up(self):
        snapshot = self._port.snapshot()
        if not snapshot.attached:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")
        if self.state == TopologyState.UP:
            return ServiceResult(
                ok=False,
                code=ResultCode.ALREADY_EXECUTED,
                message="THIS COMMAND WAS ALREADY EXECUTED FOR THIS TOPOLOGY",
                status=snapshot.status,
            )
        if self.state not in {TopologyState.DEFINED, TopologyState.DOWN, TopologyState.FAILED}:
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_UP_FAILED,
                message="TOPOLOGY CANNOT START FROM " + self.state.value.upper(),
            )
        self._transition(TopologyState.STARTING)
        try:
            result = self._port.topology_up()
        except Exception as exc:
            detail = str(exc)
            cleanup_errors = self._rollback_failed_start(detail)
            rollback_detail = self._port.snapshot().detail
            if rollback_detail and rollback_detail not in detail:
                detail += " | " + rollback_detail
            if not cleanup_errors:
                self._port.detach()
                self._transition(TopologyState.UNDEFINED)
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_UP_FAILED,
                message=(
                    "Topology startup raised an unexpected error; cleanup remains incomplete"
                    if cleanup_errors
                    else "Topology startup raised an unexpected error"
                ),
                data={"errors": cleanup_errors} if cleanup_errors else None,
                status=self._port.snapshot().status if self._port.snapshot().attached else None,
                detail=detail,
            )
        state = self._sync_runtime_state(result)
        if state != TopologyState.UP:
            snapshot = self._port.snapshot()
            status = snapshot.status if snapshot.status is not None else (result if isinstance(result, int) else None)
            detail = snapshot.detail
            cleanup_errors = self._rollback_failed_start(detail)
            detail = self._port.snapshot().detail or detail
            if not cleanup_errors:
                self._port.detach()
                self._transition(TopologyState.UNDEFINED)
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_UP_FAILED,
                message=(
                    "Topology startup failed; cleanup remains incomplete"
                    if cleanup_errors
                    else (detail or "Topology startup failed and the topology was undefined")
                ),
                data={"errors": cleanup_errors} if cleanup_errors else None,
                status=status,
                detail=detail,
            )
        self._transition(TopologyState.UP)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP, data=self._port.compatibility_executor())

    def down(self):
        if not self._port.snapshot().attached:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")
        if self.state == TopologyState.UP:
            self._transition(TopologyState.STOPPING)
        failure = self._teardown("Topology cleanup failed; the executor was preserved for retry")
        if failure is not None:
            return failure
        self._transition(TopologyState.DOWN)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DOWN)

    def clean(self):
        if not self._port.snapshot().attached:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")
        if self.state == TopologyState.UP:
            self._transition(TopologyState.STOPPING)
        failure = self._teardown("Topology cleanup failed; the topology remains defined for retry")
        if failure is not None:
            return failure
        self._port.detach()
        self._transition(TopologyState.UNDEFINED)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_CLEAN)

    def destroy(self):
        if not self._port.snapshot().attached:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")
        if self.state == TopologyState.UP:
            self._transition(TopologyState.STOPPING)
        failure = self._teardown("Topology cleanup failed; persistent images were not removed and the executor was preserved")
        if failure is not None:
            return failure
        image_errors = self._destroy_images()
        if image_errors:
            detail = self._cleanup_detail(image_errors)
            self._port.set_cleanup(image_errors, required=False, status=-10, detail=detail)
            self._port.mark_cleanup_pending()
            self._transition(TopologyState.CLEANUP_PENDING)
            return self._cleanup_failure("Persistent topology state could not be removed; the executor was preserved for retry")
        self._port.detach()
        self._transition(TopologyState.DESTROYED)
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DESTROYED)

    def _rollback_failed_start(self, startup_detail):
        try:
            errors = self._structured_cleanup_errors(self._port.rollback_failed_start())
            snapshot = self._port.snapshot()
            status = snapshot.status if snapshot.status is not None else -10
            self._port.set_cleanup(errors, required=bool(errors), status=status, detail=snapshot.detail)
            return errors
        except Exception as exc:
            error = cleanup_failure_record(exc, resource_type="executor", resource_id="topology", operation="rollback")
            errors = self._structured_cleanup_errors(self._port.snapshot().cleanup_errors)
            errors.append(error)
            detail = ((startup_detail + " | ") if startup_detail else "") + "Rollback warnings: " + self._cleanup_detail(errors)
            self._port.set_cleanup(errors, required=True, status=-10, detail=detail)
            return errors

    def _teardown(self, failure_message):
        if not self._cleanup_required():
            return None
        try:
            result = self._port.topology_down()
        except Exception as exc:
            error = cleanup_failure_record(exc, resource_type="executor", resource_id="topology", operation="topologyDown")
            errors = self._structured_cleanup_errors(self._port.snapshot().cleanup_errors)
            errors.append(error)
            detail = self._cleanup_detail(errors)
            self._port.set_cleanup(errors, required=True, status=-10, detail=detail)
            return self._cleanup_failure(failure_message)
        snapshot = self._port.snapshot()
        if snapshot.lifecycle_state is None and result in (0, None) and snapshot.status is None:
            state = self._transition(TopologyState.DOWN, force=True)
        else:
            state = self._sync_runtime_state(result)
        if state not in {TopologyState.DOWN, TopologyState.DEFINED}:
            return self._cleanup_failure(failure_message)
        return None

    def _cleanup_required(self):
        snapshot = self._port.snapshot()
        runtime_state = snapshot.lifecycle_state
        if runtime_state is not None:
            if runtime_state in {TopologyState.UP, TopologyState.STARTING, TopologyState.STOPPING, TopologyState.FAILED, TopologyState.CLEANUP_PENDING}:
                return True
            if runtime_state == TopologyState.DEFINED:
                return True
            return False
        if snapshot.cleanup_required:
            return True
        return self.state not in {TopologyState.DOWN, TopologyState.UNDEFINED}

    def _cleanup_failure(self, message):
        snapshot = self._port.snapshot()
        errors = self._structured_cleanup_errors(snapshot.cleanup_errors)
        detail = snapshot.detail
        if not errors:
            errors = [cleanup_failure_record(RuntimeError(detail or "cleanup returned a failure status"), resource_type="executor", resource_id="topology", operation="topologyDown")]
        return ServiceResult(
            ok=False,
            code=ResultCode.TOPOLOGY_DOWN_FAILED,
            message=message,
            data={"errors": errors},
            status=snapshot.status if snapshot.status is not None else -10,
            detail=detail or self._cleanup_detail(errors),
        )

    def _destroy_images(self):
        # Keep the old module-level seams patchable for lifecycle tests and
        # downstream integrations while the adapter owns runtime access.
        from niep.application import service as compatibility_module

        images_path = str(asset_directory("VEM", "IMAGES", description="VEM/IMAGES"))
        cleanup_errors = []
        for resource_type, resource_id in self._port.image_ids():
            image_path = join(images_path, str(resource_id))
            cleanup_key = (resource_type, str(resource_id), "remove_persistent_state")
            if self._port.persistent_done(cleanup_key):
                continue
            try:
                image_exists = compatibility_module.exists(image_path)
            except Exception as exc:
                cleanup_errors.append({"resource_type": resource_type, "resource_id": str(resource_id), "operation": "remove_persistent_state", "message": str(exc)})
                continue
            if not image_exists:
                self._port.mark_persistent_done(cleanup_key)
                continue
            try:
                compatibility_module.rmtree(image_path)
                self._port.mark_persistent_done(cleanup_key)
            except FileNotFoundError:
                self._port.mark_persistent_done(cleanup_key)
            except Exception as exc:
                cleanup_errors.append({"resource_type": resource_type, "resource_id": str(resource_id), "operation": "remove_persistent_state", "message": str(exc)})
        return cleanup_errors

    def _cleanup_detail(self, errors):
        return " | ".join(str(error["resource_type"]) + " " + str(error["resource_id"]) + " " + str(error["operation"]) + " failed: " + str(error["message"]) for error in errors)

    def _structured_cleanup_errors(self, errors):
        structured = []
        if errors is None:
            return structured
        if isinstance(errors, (dict, str, bytes)) or not hasattr(errors, "__iter__"):
            errors = [errors]
        for error in errors:
            structured.append(cleanup_failure_record(error, resource_type="unknown", resource_id="unknown", operation="cleanup"))
        return structured

    # Historical in-process callers used the camelCase spelling.  Keep this
    # tiny alias at the application boundary; the implementation remains
    # entirely port-backed.
    _structuredCleanupErrors = _structured_cleanup_errors

    def is_up(self):
        snapshot = self._port.snapshot()
        if not snapshot.attached:
            return False
        if self.state == TopologyState.UP:
            return True
        if snapshot.lifecycle_state is None and snapshot.status == 0:
            self._transition(TopologyState.UP, force=True)
        return self.state == TopologyState.UP

    def vm_ids(self):
        return list(self._port.snapshot().vm_ids) if self.is_up() else []

    def container_ids(self):
        return list(self._port.snapshot().container_ids) if self.is_up() else []

    def vnf_ids(self):
        return list(self._port.snapshot().vnf_ids) if self.is_up() else []

    def sfc_ids(self):
        return list(self._port.snapshot().sfc_ids) if self.is_up() else []

    def get_vm(self, vm_id):
        return self._port.get_resource("vm", vm_id) if self.is_up() else None

    def get_container(self, container_id):
        return self._port.get_resource("container", container_id) if self.is_up() else None

    def get_vnf(self, vnf_id):
        return self._port.get_resource("vnf", vnf_id) if self.is_up() else None

    def get_sfc(self, sfc_id):
        return self._port.get_resource("sfc", sfc_id) if self.is_up() else None

    def mininet_pingall(self):
        return self._port.mininet_pingall()

    def mininet_node_command(self, node_id, command):
        return self._port.mininet_node_command(node_id, command)

    def with_mininet_console(self, console):
        return self._port.with_mininet_console(console)


__all__ = ["EXECUTERERRORS", "PARSERERRORS", "TopologyService"]
