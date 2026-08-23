"""Deprecated compatibility shim; use :mod:`niep.runtime.docker`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.DockerRuntime is deprecated; use niep.runtime.docker; removal planned for NIEP 1.3.0", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.docker")
