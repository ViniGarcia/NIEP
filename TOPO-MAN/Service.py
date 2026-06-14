from os.path import abspath
from shutil import rmtree

from Executer import Executer
from Parser import PlatformParser
from Result import ResultCode, ServiceResult


PARSERERRORS = {-1: "Invalid definition file path or invalid key included",
                -2: "Invalid data type included as a key value",
                -3: "Invalid VNF/VM configuration provided",
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
                -14: "Inconsistent in In/Out and Out/In poits"}

EXECUTERERRORS = {-1: "Mininet network interfaces mapping failed",
                  -2: "Invalid definition of Mininet network interface",
                  -3: "Unrecognized Mininet network interface",
                  -4: "Parser error detected"}


class TopologyService:
    def __init__(self):
        self.executor = None

    def define(self, definition_path):
        parser = PlatformParser(definition_path)
        if parser.STATUS != 0:
            return ServiceResult(
                ok=False,
                code=ResultCode.PARSER_ERROR,
                message=PARSERERRORS.get(parser.STATUS, "Parser error"),
                data=parser,
                status=parser.STATUS,
                detail=getattr(parser, 'DETAIL', ''),
            )

        executor = Executer(parser)
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

        self.executor.topologyUp()
        if self.executor.STATUS != 0:
            status = self.executor.STATUS
            self.executor = None
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_UP_FAILED,
                message="PROBLEMS ON TOPOLOGY DEFINITION ON UP PROCESS - TOPOLOGY UNDEFINED",
                status=status,
            )

        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_UP, data=self.executor)

    def down(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        self.executor.topologyDown()
        if self.executor.STATUS is not None:
            status = self.executor.STATUS
            self.executor = None
            return ServiceResult(
                ok=False,
                code=ResultCode.TOPOLOGY_DOWN_FAILED,
                message="PROBLEMS ON TOPOLOGY DEFINITION ON DOWN PROCESS - TOPOLOGY UNDEFINED",
                status=status,
            )

        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DOWN)

    def clean(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        if self.executor.STATUS == 0:
            self.executor.topologyDown()
        self.executor = None
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_CLEAN)

    def destroy(self):
        if self.executor is None:
            return ServiceResult(ok=False, code=ResultCode.NO_TOPOLOGY, message="NO TOPOLOGY DEFINED")

        if self.executor.STATUS == 0:
            self.executor.topologyDown()

        images_path = '/'.join(abspath(__file__).split('/')[:-2] + ['VEM', 'IMAGES'])
        for vnf_id in self.executor.VNFS:
            rmtree(images_path + '/' + self.executor.VNFS[vnf_id].ID, ignore_errors=True)
        for vm_id in self.executor.VMS:
            rmtree(images_path + '/' + self.executor.VMS[vm_id].ID, ignore_errors=True)

        self.executor = None
        return ServiceResult(ok=True, code=ResultCode.TOPOLOGY_DESTROYED)

    def is_up(self):
        return self.executor is not None and self.executor.STATUS == 0

    def vm_ids(self):
        if not self.is_up():
            return []
        return list(self.executor.VMS.keys())

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
        result = vm.sshVM(user, passwd)
        return ServiceResult(ok=(result == 0), code=ResultCode.VM_SSH, status=result)


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
        sfc.checkStatusSFC()
        result = sfc.wakeSFC()
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.SFC_ALREADY_UP, message="SFC ALREADY UP")
        return ServiceResult(ok=True, code=ResultCode.SFC_UP, status=result)

    def down(self, sfc_id):
        sfc = self.topology.get_sfc(sfc_id)
        if sfc is None:
            return ServiceResult(ok=False, code=ResultCode.SFC_NOT_FOUND, message="SFC NOT FOUND")
        sfc.checkStatusSFC()
        result = sfc.sleepSFC()
        if result is None:
            return ServiceResult(ok=False, code=ResultCode.INVALID_SFC_STATUS, message="INVALID SFC STATUS")
        if result == -1:
            return ServiceResult(ok=False, code=ResultCode.SFC_ALREADY_DOWN, message="SFC ALREADY DOWN")
        return ServiceResult(ok=True, code=ResultCode.SFC_DOWN, status=result)
