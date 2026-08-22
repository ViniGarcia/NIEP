#!/usr/bin/env python3
"""Deprecated CLI shim; use ``python -m niep.interfaces.cli``."""

import warnings
from niep.interfaces.cli import NIEPCLI

warnings.warn(
    "CLI/CLI.py is deprecated; use the installed NIEP package",
    DeprecationWarning,
    stacklevel=2,
)


def main():
    NIEPCLI().cmdloop()


if __name__ == "__main__":
    main()
