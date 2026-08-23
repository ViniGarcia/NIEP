"""Compatibility exports for application use cases.

Lifecycle state is implemented by :mod:`niep.application.topology_service`
and resource use cases by :mod:`niep.application.resource_services`.  This
module remains the stable import path used by older integrations.
"""

from os.path import exists  # noqa: F401 - legacy monkeypatch seam
from shutil import rmtree  # noqa: F401 - legacy monkeypatch seam

from niep.application.resource_services import ContainerService, SFCService, VMService, VNFService
from niep.application.topology_service import EXECUTERERRORS, PARSERERRORS, TopologyService

__all__ = [
    "ContainerService",
    "EXECUTERERRORS",
    "PARSERERRORS",
    "SFCService",
    "TopologyService",
    "VMService",
    "VNFService",
]
