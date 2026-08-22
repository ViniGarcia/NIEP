"""Deprecated compatibility shim; use :mod:`niep.runtime.docker`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.DockerRuntime is deprecated; use niep.runtime.docker", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.docker")
