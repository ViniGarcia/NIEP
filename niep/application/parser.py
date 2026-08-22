"""Compatibility facade over the neutral topology loader and validator.

Historically ``PlatformParser`` also constructed every runtime object. It now
only exposes neutral specs; callers that need concrete objects must invoke
``RuntimeFactory`` explicitly.
"""

from __future__ import annotations

import random
from os.path import abspath, dirname

from niep.domain.spec import (
    ConnectionSpec, ContainerSpec, InterfaceSpec, MininetControllerSpec,
    MininetHostSpec, MininetOVSSwitchSpec, MininetSwitchSpec, SFCSpec,
    TopologySpec, VMSpec, VNFSpec,
)
from niep.domain.topology import ValidationIssue, ValidationResult
from .factory import RuntimeFactory
from .loader import PathResolver, TopologyLoader, resolve_path
from .validator import TopologyValidator

class PlatformParser:
    """Read, validate and expose a :class:`TopologySpec` without materializing."""

    def __init__(self, jsonFilePath, *, loader: TopologyLoader | None = None,
                 validator: TopologyValidator | None = None):
        self.SOURCE = abspath(str(jsonFilePath))
        self.JSON = None
        self.STATUS = None
        self.ID = ""
        self.VMS = []
        self.VNFS = []
        self.SFCS = []
        self.CONTAINERS = []
        self.VM_SPECS = []
        self.VNF_SPECS = []
        self.SFC_SPECS = []
        self.CONTAINER_SPECS = []
        self.MNHOSTS = []
        self.MNSWITCHES = []
        self.MNCONTROLLER = []
        self.MNOVSES = []
        self.CONNECTIONS = []
        self.DETAIL = ""
        self.ERROR = None
        self.SPEC = None
        self.BASE_DIR = dirname(self.SOURCE)
        self.loader = loader or TopologyLoader()
        self.validator = validator or TopologyValidator(self.loader)
        self.RESULT: ValidationResult | None = None

        loaded = self.loader.load_result(self.SOURCE)
        if loaded.value is None:
            self._apply_result(loaded)
            return
        document = loaded.value
        self.JSON = dict(document.data)
        if "CONTAINERS" not in self.JSON:
            self.JSON["CONTAINERS"] = []
        if isinstance(self.JSON.get("ID"), str):
            self.ID = self.JSON["ID"]

        result = self.validator.validate(document)
        # A loader issue is already carried by the validator. If a custom
        # validator returns only a spec, retain loader diagnostics as well.
        self._apply_result(result)

    def _apply_result(self, result: ValidationResult):
        self.RESULT = result
        issue = result.first_issue
        if issue is not None:
            self.STATUS = issue.code
            self.DETAIL = result.detail()
            self.ERROR = {
                "message": issue.message,
                "field": issue.field,
                "value": issue.value,
                "file": issue.file or self.SOURCE,
            }
            if issue.line is not None:
                self.ERROR["line"] = issue.line
            return
        self.STATUS = 0
        self.SPEC = result.value
        if self.SPEC is None:
            return
        self.ID = self.SPEC.id
        self.VM_SPECS = list(self.SPEC.vms)
        self.VNF_SPECS = list(self.SPEC.vnfs)
        self.SFC_SPECS = list(self.SPEC.sfcs)
        self.CONTAINER_SPECS = list(self.SPEC.containers)
        # Legacy attributes now deliberately contain neutral value objects.
        self.VMS = list(self.SPEC.vms)
        self.VNFS = list(self.SPEC.vnfs)
        self.SFCS = list(self.SPEC.sfcs)
        self.CONTAINERS = list(self.SPEC.containers)
        self.MNHOSTS = list(self.SPEC.mininet_hosts)
        self.MNSWITCHES = list(self.SPEC.mininet_switches)
        self.MNCONTROLLER = list(self.SPEC.mininet_controllers)
        self.MNOVSES = list(self.SPEC.mininet_ovs_switches)
        self.CONNECTIONS = list(self.SPEC.connections)

    def fail(self, status, message, field=None, value=None, file=None, line=None):
        issue = ValidationIssue(status, message, field=field, file=file or self.SOURCE,
                                line=line, value=value)
        self._apply_result(ValidationResult.failure(issue))
        return status

    def resolvePath(self, filePath):
        return self.loader.resolve_path(filePath, self.SOURCE)

    @staticmethod
    def checkIP(value):
        return 0 if TopologyValidator.check_ip(value) else -1

    @staticmethod
    def checkMAC(value):
        return 0 if TopologyValidator.check_mac(value) else -1

    def generateMAC(self, lastDigitsTuple):
        if isinstance(lastDigitsTuple, int) and 0 <= lastDigitsTuple < 100:
            return "ff:ff:ff:ff:ff:" + f"{lastDigitsTuple:02d}"
        self.STATUS = -5
        return -5

    @staticmethod
    def randomizeMAC():
        values = "0123456789abcdef"
        return "b0:" + ":".join("".join(random.choice(values) for _ in range(2)) for _ in range(5))

    @staticmethod
    def isint(value):
        try:
            int(value)
            return True
        except (TypeError, ValueError):
            return False

    def materialize(self, factory: RuntimeFactory | None = None):
        """Explicit compatibility helper; normal parsing does not call it."""

        if self.STATUS != 0 or self.SPEC is None:
            return None
        return (factory or RuntimeFactory()).materialize(self.SPEC)


# Public imports kept here because older callers imported the types from the
# parser module. None of these imports load optional runtime dependencies.
__all__ = [
    "ConnectionSpec", "ContainerSpec", "InterfaceSpec", "MininetControllerSpec",
    "MininetHostSpec", "MininetOVSSwitchSpec", "MininetSwitchSpec", "SFCSpec",
    "TopologyLoader", "TopologySpec", "TopologyValidator", "ValidationIssue",
    "ValidationResult", "VMSpec", "VNFSpec", "PathResolver", "RuntimeFactory",
    "PlatformParser", "resolve_path",
]
