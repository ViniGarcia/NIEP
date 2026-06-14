from dataclasses import dataclass
from enum import Enum


class ResultCode(str, Enum):
    ACTION_NOT_FOUND = "action_not_found"
    ALREADY_EXECUTED = "already_executed"
    ARP_PROBLEMS = "arp_problems"
    COMMAND_ERROR = "command_error"
    DEFINED = "defined"
    EXECUTER_ERROR = "executer_error"
    INVALID_COMMAND_ARGS = "invalid_command_args"
    INVALID_ACTION_ARGS = "invalid_action_args"
    INVALID_SFC_STATUS = "invalid_sfc_status"
    INVALID_VM_STATUS = "invalid_vm_status"
    INVALID_VNF_STATUS = "invalid_vnf_status"
    MANAGEMENT_ADDRESS = "management_address"
    MANAGEMENT_UNREACHABLE = "management_unreachable"
    MININET_RESULT = "mininet_result"
    NO_TOPOLOGY = "no_topology"
    PARSER_ERROR = "parser_error"
    SFC_ALREADY_DOWN = "sfc_already_down"
    SFC_ALREADY_UP = "sfc_already_up"
    SFC_DOWN = "sfc_down"
    SFC_NOT_FOUND = "sfc_not_found"
    SFC_NOT_READY = "sfc_not_ready"
    SFC_NOT_UP = "sfc_not_up"
    SFC_UP = "sfc_up"
    STATUS = "status"
    TOPOLOGY_CLEAN = "topology_clean"
    TOPOLOGY_DESTROYED = "topology_destroyed"
    TOPOLOGY_DOWN = "topology_down"
    TOPOLOGY_DOWN_FAILED = "topology_down_failed"
    TOPOLOGY_UP = "topology_up"
    TOPOLOGY_UP_FAILED = "topology_up_failed"
    TOPOLOGY_NOT_UP = "topology_not_up"
    UNKNOWN_COMMAND = "unknown_command"
    UNDEFINED_ACTION = "undefined_action"
    VM_NOT_FOUND = "vm_not_found"
    VM_NOT_UP = "vm_not_up"
    VM_SSH = "vm_ssh"
    VNF_ACTION = "vnf_action"
    VNF_ALREADY_DOWN = "vnf_already_down"
    VNF_ALREADY_UP = "vnf_already_up"
    VNF_DOES_NOT_EXIST = "vnf_does_not_exist"
    VNF_DOWN = "vnf_down"
    VNF_NOT_FOUND = "vnf_not_found"
    VNF_NOT_UP = "vnf_not_up"
    VNF_SCRIPT = "vnf_script"
    VNF_UP = "vnf_up"


@dataclass
class ServiceResult:
    ok: bool
    code: ResultCode
    message: str = ""
    data: object = None
    status: int = None
    detail: str = ""

    def __post_init__(self):
        if isinstance(self.code, str):
            self.code = ResultCode(self.code)

    @classmethod
    def success(cls, code, message="", data=None, status=None, detail=""):
        return cls(True, code, message=message, data=data, status=status, detail=detail)

    @classmethod
    def failure(cls, code, message, data=None, status=None, detail=""):
        return cls(False, code, message=message, data=data, status=status, detail=detail)

    def to_dict(self):
        result = {
            "ok": self.ok,
            "code": self.code.value if isinstance(self.code, ResultCode) else str(self.code),
            "message": self.message,
        }
        if self.data is not None:
            result["data"] = self._json_safe(self.data)
        if self.status is not None:
            result["status"] = self.status
        if self.detail:
            result["detail"] = self.detail
        return result

    def cli_message(self, include_status=False):
        message = self.message
        if include_status and self.status is not None:
            message += " (" + str(self.status) + ")"
        return message

    def _json_safe(self, value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [self._json_safe(item) for item in value]
        if isinstance(value, tuple):
            return [self._json_safe(item) for item in value]
        if isinstance(value, dict):
            return {str(key): self._json_safe(item) for key, item in value.items()}
        return str(value)
