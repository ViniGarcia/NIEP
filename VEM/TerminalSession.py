"""Deprecated compatibility shim; use :mod:`niep.runtime.terminal_session`."""
from importlib import import_module
import sys
import warnings
warnings.warn("VEM.TerminalSession is deprecated; use niep.runtime.terminal_session", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.runtime.terminal_session")
