"""Deprecated compatibility shim; use :mod:`niep.runtime.vm_network`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.VMNetworkRuntime is deprecated; use niep.runtime.vm_network", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.vm_network")
