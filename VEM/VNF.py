"""Deprecated compatibility shim; use :mod:`niep.runtime.vnf`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.VNF is deprecated; use niep.runtime.vnf; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.vnf")
