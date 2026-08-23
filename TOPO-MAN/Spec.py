"""Deprecated compatibility shim; use :mod:`niep.domain.spec`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.Spec is deprecated; use niep.domain.spec; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.domain.spec")
