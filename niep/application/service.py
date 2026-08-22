from os.path import exists, join
from shutil import rmtree

from niep.application.executer import Executer
from niep.application.factory import RuntimeFactory
from niep.application.parser import PlatformParser
from niep.domain.result import ResultCode, ServiceResult
from niep.paths import asset_directory
from niep.runtime.errors import RuntimeFailure, cleanup_failure_record


PARSERERRORS = {-1: "Invalid definition file path or invalid key included",
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
                -14: "Inconsistent In/Out and Out/In points"}

EXECUTERERRORS = {-1: "Mininet network interfaces mapping failed",
                  -2: "Invalid definition of Mininet network interface",
                  -3: "Unrecognized Mininet network interface",
                  -4: "Parser error detected"}


class TopologyService:
    def __init__(self, runtime_factory=None, executor_factory=None, parser_factory=None):
        self.executor = None
        # Keep all materialization seams injectable for host-only tests and
        # alternate runtime adapters.
        self.runtime_factory = (runtime_factory if runtime_factory is not None
                                else RuntimeFactory())
        self.executor_factory = (executor_factory if executor_factory is not None
                                  else Executer)
        self.parser_factory = (parser_factory if parser_factory is not None
                               else PlatformParser)

    def define(self, definition_path):
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
            detail = getattr(parser, 'DETAIL', '')
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
            executor = self.executor_factory(configuration)
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
        if executor.STATUS is not None:
            return ServiceResult(
                ok=False,
                code=ResultCode.EXECUTER_ERROR,
                message=EXECUTERERRORS.get(executor.STATUS, "Executer error"),
                data=executor,
                status=executor.STATUS,
            )

        self.executor = executor
        return ServiceResult(ok=True, code=ResultCode.DEFINED, data=executor)

    def up(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        if self.executor.STATUS is not None:
            return ServiceResult(
                ok=False,
                code=ResultCode.ALREADY_EXECUTED,
                message="THIS COMMAND WAS ALREADY EXECUTED FOR THIS TOPOLOGY",
                status=self.executor.STATUS,
            )

        try:
            self.executor.topologyUp()
        except Exception as exc:
            detail = str(exc)
            cleanupErrors = self._rollbackFailedStart(detail)
            rollbackDetail = getattr(self.executor, 'DETAIL', '')
            if rollbackDetail and rollbackDetail not in detail:
                detail += " | " + rollbackDetail
            if not cleanupErrors:
                self.executor = None
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_UP_FAILED,
                message=(
                    "Topology startup raised an unexpected error; cleanup remains incomplete"
                    if cleanupErrors
                    else "Topology startup raised an unexpected error"
                ),
                data={"errors": cleanupErrors} if cleanupErrors else None,
                status=getattr(self.executor, 'STATUS', None) if self.executor is not None else None,
                detail=detail,
            )
        if self.executor.STATUS != 0:
            status = self.executor.STATUS
            detail = getattr(self.executor, 'DETAIL', '')
            cleanupErrors = self._rollbackFailedStart(detail)
            detail = getattr(self.executor, 'DETAIL', '') or detail
            if not cleanupErrors:
                self.executor = None
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_UP_FAILED,
                message=(
                    "Topology startup failed; cleanup remains incomplete"
                    if cleanupErrors
                    else (detail or "Topology startup failed and the topology was undefined")
                ),
                data={"errors": cleanupErrors} if cleanupErrors else None,
                status=status,
                detail=detail,
            )

        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP, data=self.executor)

    def down(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        failure = self._teardown("Topology cleanup failed; the executor was preserved for retry")
        if failure is not None:
            return failure

        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DOWN)

    def clean(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        failure = self._teardown("Topology cleanup failed; the topology remains defined for retry")
        if failure is not None:
            return failure
        self.executor = None
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_CLEAN)

    def destroy(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        failure = self._teardown(
            "Topology cleanup failed; persistent images were not removed and the executor was preserved"
        )
        if failure is not None:
            return failure

        imageErrors = self._destroyImages()
        if imageErrors:
            self.executor.CLEANUP_ERRORS = imageErrors
            self.executor.CLEANUP_REQUIRED = False
            self.executor.STATUS = -10
            self.executor.DETAIL = self._cleanupDetail(imageErrors)
            return self._cleanupFailure(
                "Persistent topology state could not be removed; the executor was preserved for retry"
            )

        self.executor = None
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DESTROYED)

    def _rollbackFailedStart(self, startupDetail):
        try:
            errors = self.executor.rollbackFailedStart()
            errors = self._structuredCleanupErrors(errors)
            self.executor.CLEANUP_ERRORS = errors
            return errors
        except Exception as exc:
            error = cleanup_failure_record(
                exc,
                resource_type="executor",
                resource_id="topology",
                operation="rollback",
            )
            errors = self._structuredCleanupErrors(
                getattr(self.executor, 'CLEANUP_ERRORS', [])
            )
            errors.append(error)
            self.executor.CLEANUP_ERRORS = errors
            self.executor.CLEANUP_REQUIRED = True
            self.executor.STATUS = -10
            self.executor.DETAIL = (
                (startupDetail + " | ") if startupDetail else ""
            ) + "Rollback warnings: " + self._cleanupDetail(errors)
            return errors

    def _teardown(self, failureMessage):
        if not self._cleanupRequired():
            return None

        try:
            status = self.executor.topologyDown()
        except Exception as exc:
            error = cleanup_failure_record(
                exc,
                resource_type="executor",
                resource_id="topology",
                operation="topologyDown",
            )
            errors = self._structuredCleanupErrors(
                getattr(self.executor, "CLEANUP_ERRORS", [])
            )
            errors.append(error)
            self.executor.CLEANUP_ERRORS = errors
            self.executor.CLEANUP_REQUIRED = True
            self.executor.STATUS = -10
            self.executor.DETAIL = self._cleanupDetail(errors)
            return self._cleanupFailure(failureMessage)

        if (
            status not in (0, None)
            or bool(getattr(self.executor, 'CLEANUP_REQUIRED', False))
            or self.executor.STATUS is not None
        ):
            return self._cleanupFailure(failureMessage)
        return None

    def _cleanupRequired(self):
        if hasattr(self.executor, 'CLEANUP_REQUIRED'):
            return bool(self.executor.CLEANUP_REQUIRED)
        return self.executor.STATUS is not None

    def _cleanupFailure(self, message):
        errors = self._structuredCleanupErrors(
            getattr(self.executor, 'CLEANUP_ERRORS', [])
        )
        detail = getattr(self.executor, 'DETAIL', '')
        if not errors:
            errors = [cleanup_failure_record(
                RuntimeError(detail or "cleanup returned a failure status"),
                resource_type="executor",
                resource_id="topology",
                operation="topologyDown",
            )]
        return ServiceResult(
            ok=False,
            code=ResultCode.TOPOLOGY_DOWN_FAILED,
            message=message,
            data={"errors": errors},
            status=getattr(self.executor, 'STATUS', -10),
            detail=detail or self._cleanupDetail(errors),
        )

    def _destroyImages(self):
        imagesPath = str(asset_directory('VEM', 'IMAGES', description='VEM/IMAGES'))
        images = []
        images.extend(("vnf_image", vnf.ID) for vnf in self.executor.VNFS.values())
        images.extend(("vm_image", vm.ID) for vm in self.executor.VMS.values())

        cleanupErrors = []
        completed = getattr(self.executor, '_PERSISTENT_STATE_COMPLETED', None)
        if completed is None:
            completed = set()
            self.executor._PERSISTENT_STATE_COMPLETED = completed
        for resourceType, resourceID in images:
            imagePath = join(imagesPath, str(resourceID))
            cleanupKey = (resourceType, str(resourceID), "remove_persistent_state")
            if cleanupKey in completed:
                continue
            try:
                imageExists = exists(imagePath)
            except Exception as exc:
                cleanupErrors.append({
                    "resource_type": resourceType,
                    "resource_id": str(resourceID),
                    "operation": "remove_persistent_state",
                    "message": str(exc),
                })
                continue
            if not imageExists:
                completed.add(cleanupKey)
                continue
            try:
                rmtree(imagePath)
                completed.add(cleanupKey)
            except FileNotFoundError:
                completed.add(cleanupKey)
            except Exception as exc:
                cleanupErrors.append({
                    "resource_type": resourceType,
                    "resource_id": str(resourceID),
                    "operation": "remove_persistent_state",
                    "message": str(exc),
                })
        return cleanupErrors

    def _cleanupDetail(self, errors):
        return " | ".join(
            str(error["resource_type"])
            + " "
            + str(error["resource_id"])
            + " "
            + str(error["operation"])
            + " failed: "
            + str(error["message"])
            for error in errors
        )

    def _structuredCleanupErrors(self, errors):
        """Normalize legacy adapter errors before exposing them to callers."""
        structured = []
        if errors is None:
            return structured
        if isinstance(errors, (dict, str, bytes)) or not hasattr(errors, "__iter__"):
            errors = [errors]
        for error in errors:
            structured.append(
                cleanup_failure_record(
                    error,
                    resource_type="unknown",
                    resource_id="unknown",
                    operation="cleanup",
                )
            )
        return structured

    def is_up(self):
        return self.executor is not None and self.executor.STATUS == 0

    def vm_ids(self):
        if not self.is_up():
            return []
        return list(self.executor.VMS.keys())

    def container_ids(self):
        if not self.is_up():
            return []
        return list(self.executor.CONTAINERS.keys())

    def vnf_ids(self):
        if not self.is_up():
            return []
        return list(self.executor.VNFS.keys())

    def sfc_ids(self):
        if not self.is_up():
            return []
        return [sfc.ID for sfc in self.executor.CONFIGURATION.SFCS]

    def get_vm(self, vm_id):
        if not self.is_up():
            return None
        return self.executor.VMS.get(vm_id)

    def get_container(self, container_id):
        if not self.is_up():
            return None
        return self.executor.CONTAINERS.get(container_id)

    def get_vnf(self, vnf_id):
        if not self.is_up():
            return None
        return self.executor.VNFS.get(vnf_id)

    def get_sfc(self, sfc_id):
        if not self.is_up():
            return None
        for sfc in self.executor.CONFIGURATION.SFCS:
            if sfc.ID == sfc_id:
                return sfc
        return None


class VMService:
    def __init__(self, topology):
        self.topology = topology

    def management(self, vm_id):
        vm = self.topology.get_vm(vm_id)
        if vm is None:
            return ServiceResult(ok=False, code=ResultCode.VM_NOT_FOUND, message="VM NOT FOUND")

        management = vm.managementVM()
        if management is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_VM_STATUS, message="INVALID VM STATUS")
        if management == -1:
            return ServiceResult(ok=False, code=ResultCode.VM_NOT_UP, message="VM IS NOT UP")
        if management == -2:
            return ServiceResult(ok=False, code=ResultCode.ARP_PROBLEMS, message="ARP PROBLEMS")
        return ServiceResult(ok=True, code=ResultCode.MANAGEMENT_ADDRESS, data=management)

    def ssh(self, vm_id, user, passwd):
        vm = self.topology.get_vm(vm_id)
        if vm is None:
            return ServiceResult(ok=False, code=ResultCode.VM_NOT_FOUND, message="VM NOT FOUND")
        try:
            result = vm.sshVM(user, passwd)
        except RuntimeFailure as exc:
            return ServiceResult(
                ok=False,
                code=ResultCode.VM_SSH,
                message="VM SSH connection could not be opened",
                data={"error": exc.to_dict()},
                status=-10,
                detail=str(exc),
            )
        return ServiceResult(ok=(result == 0), code=ResultCode.VM_SSH, status=result)


class ContainerService:
    def __init__(self, topology):
        self.topology = topology

    def exec(self, container_id, command):
        container = self.topology.get_container(container_id)
        if container is None:
            return ServiceResult(ok=False, code=ResultCode.CONTAINER_NOT_FOUND, message="CONTAINER NOT FOUND")
        try:
            exit_code, output = container.execContainer(command)
        except RuntimeFailure as exc:
            return ServiceResult(
                ok=False,
                code=ResultCode.CONTAINER_RUNTIME_ERROR,
                message="Container command could not be executed",
                data={"error": exc.to_dict()},
                status=-10,
                detail=str(exc),
            )
        return ServiceResult(
            ok=(exit_code == 0),
            code=ResultCode.CONTAINER_EXEC,
            message="" if exit_code == 0 else "Container command exited with status " + str(exit_code),
            data={'exit_code': exit_code, 'output': output},
            status=exit_code,
        )

    def open_shell(self, container_id, command):
        container = self.topology.get_container(container_id)
        if container is None:
            return ServiceResult(ok=False, code=ResultCode.CONTAINER_NOT_FOUND, message="CONTAINER NOT FOUND")
        try:
            stream = container.openShell(command)
        except RuntimeFailure as exc:
            return ServiceResult(
                ok=False,
                code=ResultCode.CONTAINER_RUNTIME_ERROR,
                message="Container shell could not be opened",
                data={"error": exc.to_dict()},
                status=-10,
                detail=str(exc),
            )
        return ServiceResult(ok=True, code=ResultCode.CONTAINER_SHELL, data=stream)


class VNFService:
    def __init__(self, topology):
        self.topology = topology

    def management(self, vnf_id):
        vnf = self.topology.get_vnf(vnf_id)
        if vnf is None:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_FOUND, message="VNF NOT FOUND")

        management = vnf.managementVNF()
        if management is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_VNF_STATUS, message="INVALID VNF STATUS")
        if management == -1:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_UP, message="VNF IS NOT UP")
        if management == -2:
            return ServiceResult(ok=False, code=ResultCode.ARP_PROBLEMS, message="ARP PROBLEMS")
        return ServiceResult(ok=True, code=ResultCode.MANAGEMENT_ADDRESS, data=management)

    def up(self, vnf_id):
        vnf = self.topology.get_vnf(vnf_id)
        if vnf is None:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_FOUND, message="VNF NOT FOUND")
        result = vnf.upVNF()
        if result is None:
            vmstatus = getattr(getattr(vnf, 'VM', None), 'VM_STATUS', None)
            return ServiceResult(
                ok=False,
                code=ResultCode.INVALID_VNF_STATUS,
                message="INVALID VNF STATUS",
                data={'VNF_STATUS': getattr(vnf, 'VNF_STATUS', None), 'VM_STATUS': vmstatus},
            )
        if result == -2:
            return ServiceResult(ok=False, code=ResultCode.VNF_DOES_NOT_EXIST, message="VNF DOES NOT EXIST")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.VNF_ALREADY_UP, message="VNF ALREADY UP")
        return ServiceResult(ok=True, code=ResultCode.VNF_UP, status=result)

    def down(self, vnf_id):
        vnf = self.topology.get_vnf(vnf_id)
        if vnf is None:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_FOUND, message="VNF NOT FOUND")
        result = vnf.sleepVNF()
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_VNF_STATUS, message="INVALID VNF STATUS")
        if result == -2:
            return ServiceResult(ok=False, code=ResultCode.VNF_DOES_NOT_EXIST, message="VNF DOES NOT EXIST")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.VNF_ALREADY_DOWN, message="VNF ALREADY DOWN")
        return ServiceResult(ok=True, code=ResultCode.VNF_DOWN, status=result)

    def action(self, vnf_id, action, args):
        vnf = self.topology.get_vnf(vnf_id)
        if vnf is None:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_FOUND, message="VNF NOT FOUND")

        result = vnf.controlVNF(action, args)
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.UNDEFINED_ACTION, message="UNDEFINED ACTION")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_UP, message="VNF IS NOT UP")
        if result == -2:
            return ServiceResult(ok=False, code=ResultCode.MANAGEMENT_UNREACHABLE, message="VNF MANAGEMENT IS NOT ACCESIBLE")
        if result == -3:
            return ServiceResult(ok=False, code=ResultCode.ACTION_NOT_FOUND, message="VNF ACTION DOES NOT EXIST")
        if result == -4:
            return ServiceResult(ok=False, code=ResultCode.INVALID_ACTION_ARGS, message="INVALID ARGUMENTS FOR THE REQUESTED VNF ACTION")
        return ServiceResult(ok=True, code=ResultCode.VNF_ACTION, data=result)

    def script(self, vnf_id, script_normal, script_error):
        vnf = self.topology.get_vnf(vnf_id)
        if vnf is None:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_FOUND, message="VNF NOT FOUND")

        result = vnf.scriptVNF(script_normal, script_error)
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_UP, message="VNF IS NOT UP")
        if result == -2:
            return ServiceResult(ok=False, code=ResultCode.MANAGEMENT_UNREACHABLE, message="VNF MANAGEMENT IS NOT ACCESIBLE")
        return ServiceResult(ok=True, code=ResultCode.VNF_SCRIPT, data=result)


class SFCService:
    def __init__(self, topology):
        self.topology = topology

    def management(self, sfc_id):
        sfc = self.topology.get_sfc(sfc_id)
        if sfc is None:
            return ServiceResult(ok=False, code=ResultCode.SFC_NOT_FOUND, message="SFC NOT FOUND")
        if not sfc.checkStatusSFC():
            return ServiceResult(ok=False, code=ResultCode.SFC_NOT_READY, message="SFC IS NOT UP OR NOT TOTALLY UP")
        result = sfc.managementSFC()
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.SFC_NOT_UP, message="SFC IS NOT UP")
        if result == -2:
            return ServiceResult(ok=False, code=ResultCode.ARP_PROBLEMS, message="ARP PROBLEMS")
        return ServiceResult(ok=True, code=ResultCode.MANAGEMENT_ADDRESS, data=result)

    def up(self, sfc_id):
        sfc = self.topology.get_sfc(sfc_id)
        if sfc is None:
            return ServiceResult(ok=False, code=ResultCode.SFC_NOT_FOUND, message="SFC NOT FOUND")
        start = getattr(sfc, "upSFC", None)
        if callable(start):
            result = start()
        else:
            sfc.checkStatusSFC()
            result = sfc.wakeSFC()
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.SFC_ALREADY_UP, message="SFC ALREADY UP")
        if isinstance(result, list):
            return ServiceResult(
                ok=False,
                code=ResultCode.INVALID_SFC_STATUS,
                message="INVALID SFC STATUS",
                data=result,
                status=result[1] if len(result) > 1 and isinstance(result[1], int) else None,
            )
        return ServiceResult(ok=True, code=ResultCode.SFC_UP, status=result)

    def down(self, sfc_id):
        sfc = self.topology.get_sfc(sfc_id)
        if sfc is None:
            return ServiceResult(ok=False, code=ResultCode.SFC_NOT_FOUND, message="SFC NOT FOUND")
        stop = getattr(sfc, "downSFC", None)
        if callable(stop):
            result = stop()
        else:
            sfc.checkStatusSFC()
            result = sfc.sleepSFC()
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.SFC_ALREADY_DOWN, message="SFC ALREADY DOWN")
        if isinstance(result, list):
            return ServiceResult(
                ok=False,
                code=ResultCode.INVALID_SFC_STATUS,
                message="INVALID SFC STATUS",
                data=result,
                status=result[1] if len(result) > 1 and isinstance(result[1], int) else None,
            )
        return ServiceResult(ok=True, code=ResultCode.SFC_DOWN, status=result)
