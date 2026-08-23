"""Deprecated compatibility shim; use :mod:`niep.domain.result`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.Result is deprecated; use niep.domain.result; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.domain.result")
