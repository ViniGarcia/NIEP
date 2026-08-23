#!/usr/bin/env python3
"""Deprecated launcher; install NIEP and invoke ``niepctl``."""

import warnings
from importlib import import_module
import sys

warnings.warn(
    "tools/niepctl.py is deprecated; use the installed 'niepctl' entry point; removal planned for NIEP 1.3.0",
    DeprecationWarning,
    stacklevel=2,
)
_implementation = import_module("niep.interfaces.niepctl")
sys.modules[__name__] = _implementation

if __name__ == "__main__":
    _implementation.main()
