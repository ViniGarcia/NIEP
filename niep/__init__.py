"""NIEP NFV emulation platform.

The public package is intentionally small at import time.  Optional runtime
adapters (Docker, libvirt and Mininet) are loaded only by the modules that
need them, so ``import niep`` works on a regular development host.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("niep")
except PackageNotFoundError:
    __version__ = "1.2.0a1"

__all__ = ["__version__"]
