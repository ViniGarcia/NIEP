"""Resource use cases bound to the topology service port."""

from __future__ import annotations

from niep.domain.result import ResultCode, ServiceResult
from niep.runtime.errors import RuntimeFailure


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
            data={"exit_code": exit_code, "output": output},
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
            vmstatus = getattr(getattr(vnf, "VM", None), "VM_STATUS", None)
            return ServiceResult(
                ok=False,
                code=ResultCode.INVALID_VNF_STATUS,
                message="INVALID VNF STATUS",
                data={"VNF_STATUS": getattr(vnf, "VNF_STATUS", None), "VM_STATUS": vmstatus},
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

    def actions(self, vnf_id):
        """Return the VNF action catalog without dispatching an action."""
        vnf = self.topology.get_vnf(vnf_id)
        if vnf is None:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_FOUND, message="VNF NOT FOUND")
        result = vnf.controlVNF("list", [])
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.UNDEFINED_ACTION, message="UNDEFINED ACTION")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.VNF_NOT_UP, message="VNF IS NOT UP")
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
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS", data=result, status=result[1] if len(result) > 1 and isinstance(result[1], int) else None)
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
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS", data=result, status=result[1] if len(result) > 1 and isinstance(result[1], int) else None)
        return ServiceResult(ok=True, code=ResultCode.SFC_DOWN, status=result)


__all__ = ["ContainerService", "SFCService", "VMService", "VNFService"]
