#!/usr/bin/env python3
"""Deprecated launcher; install NIEP and invoke ``niepd``."""

import warnings
from importlib import import_module
import sys

warnings.warn(
    "tools/niepd.py is deprecated; use the installed 'niepd' entry point; removal planned for NIEP 1.3.0",
    DeprecationWarning,
    stacklevel=2,
)
_implementation = import_module("niep.interfaces.niepd")
sys.modules[__name__] = _implementation

if __name__ == "__main__":
    _implementation.main()
