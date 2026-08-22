"""Deprecated compatibility shim; use :mod:`niep.application.service`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.Service is deprecated; use niep.application.service", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.application.service")
