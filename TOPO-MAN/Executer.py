"""Deprecated compatibility shim; use :mod:`niep.application.executer`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.Executer is deprecated; use niep.application.executer", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.application.executer")
