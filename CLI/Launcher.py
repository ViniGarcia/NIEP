#!/usr/bin/env python3
"""Deprecated topology launcher shim."""

import sys
import warnings

warnings.warn(
    "CLI/Launcher.py is deprecated; use niep.interfaces.cli; removal planned for NIEP 1.3.0",
    DeprecationWarning,
    stacklevel=2,
)

from niep.interfaces.cli import NIEPCLI


def main():
    control = NIEPCLI()
    control.do_define(sys.argv[1])
    control.do_topoup("")
    control.cmdloop()


if __name__ == "__main__":
    main()
