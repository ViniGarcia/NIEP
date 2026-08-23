"""Deprecated compatibility shim; use :mod:`niep.runtime.container_network`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.ContainerNetworkRuntime is deprecated; use niep.runtime.container_network; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.container_network")
