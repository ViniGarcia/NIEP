#!/usr/bin/env python3
"""Deprecated CLI shim; use ``python -m niep.interfaces.cli``."""

import warnings

warnings.warn(
    "CLI/CLI.py is deprecated; use python -m niep.interfaces.cli; removal planned for NIEP 1.3.0",
    DeprecationWarning,
    stacklevel=2,
)

from niep.interfaces.cli import NIEPCLI


def main():
    NIEPCLI().cmdloop()


if __name__ == "__main__":
    main()
