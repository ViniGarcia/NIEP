"""Deprecated compatibility shim; use :mod:`niep.runtime.vm_image_store`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.VMImageStore is deprecated; use niep.runtime.vm_image_store", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.vm_image_store")
