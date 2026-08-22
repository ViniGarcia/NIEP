"""Deprecated compatibility shim; use :mod:`niep.interfaces.socket_server`."""
from importlib import import_module
import sys
import warnings
warnings.warn("TOPO-MAN.SocketServer is deprecated; use niep.interfaces.socket_server", DeprecationWarning, stacklevel=2)
sys.modules[__name__] = import_module("niep.interfaces.socket_server")
