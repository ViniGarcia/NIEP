"""Deprecated compatibility shim; use :mod:`niep.application.parser`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.Parser is deprecated; use niep.application.parser; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.application.parser")
