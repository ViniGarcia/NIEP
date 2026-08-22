"""Deprecated compatibility shim; use :mod:`niep.runtime.vm`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.VM is deprecated; use niep.runtime.vm", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.vm")
