"""Deprecated compatibility shim; use :mod:`niep.runtime.infrastructure`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.InfrastructureRuntime is deprecated; use niep.runtime.infrastructure", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.infrastructure")
