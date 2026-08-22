"""Deprecated compatibility shim; use :mod:`niep.runtime.click_on_osv`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.ClickOnOSv is deprecated; use niep.runtime.click_on_osv", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.click_on_osv")
