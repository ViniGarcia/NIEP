"""Deprecated compatibility shim; use :mod:`niep.runtime.libvirt`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.LibvirtRuntime is deprecated; use niep.runtime.libvirt", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.libvirt")
