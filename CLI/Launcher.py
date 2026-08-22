#!/usr/bin/env python3
"""Deprecated topology launcher shim."""

import sys
import warnings

from niep.interfaces.cli import NIEPCLI

warnings.warn(
    "CLI/Launcher.py is deprecated; use the NIEP package",
    DeprecationWarning,
    stacklevel=2,
)


def main():
    control = NIEPCLI()
    control.do_define(sys.argv[1])
    control.do_topoup("")
    control.cmdloop()


if __name__ == "__main__":
    main()
