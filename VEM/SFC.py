"""Deprecated compatibility shim; use :mod:`niep.runtime.sfc`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.SFC is deprecated; use niep.runtime.sfc; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.sfc")
