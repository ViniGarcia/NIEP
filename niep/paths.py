"""Resolve assets that live beside the installable NIEP package.

The Python package intentionally does not ship the VM images, POX checkout or
CLI history files.  Source/editable installs can discover those assets from
the repository checkout; installed deployments must opt in explicitly with
``NIEP_ROOT``.  Keeping this policy in one module avoids silently resolving
paths relative to whichever process happened to launch NIEP.
"""

from __future__ import annotations

import os
from pathlib import Path


class NIEPPathError(RuntimeError):
    """Raised when an external NIEP asset cannot be resolved."""


def repository_root() -> Path:
    """Return the configured checkout root or raise a useful error.

    ``NIEP_ROOT`` takes precedence so a wheel installation can use assets from
    a separately provisioned checkout.  Without it, only a real source
    checkout (identified by its ``VEM`` directory) is accepted.
    """

    configured = os.environ.get("NIEP_ROOT")
    if configured:
        root = Path(configured).expanduser().resolve()
        if not root.is_dir():
            raise NIEPPathError(
                "NIEP_ROOT does not point to a directory: " + str(root)
            )
        return root

    candidate = Path(__file__).resolve().parent.parent
    if (candidate / "VEM").is_dir():
        return candidate

    raise NIEPPathError(
        "NIEP checkout assets are unavailable; set NIEP_ROOT to the NIEP "
        "checkout containing VEM/, CONFS/ and any required external assets"
    )


def asset_path(*parts: str, description: str | None = None) -> Path:
    """Resolve an existing checkout asset and report missing assets clearly."""

    path = repository_root().joinpath(*parts)
    if not path.exists():
        label = description or "/".join(parts)
        raise NIEPPathError(
            "NIEP asset not found: "
            + label
            + " (resolved to "
            + str(path)
            + "); set NIEP_ROOT to a checkout containing this asset"
        )
    return path


def asset_directory(*parts: str, description: str | None = None) -> Path:
    """Resolve an existing directory asset."""

    path = asset_path(*parts, description=description)
    if not path.is_dir():
        label = description or "/".join(parts)
        raise NIEPPathError("NIEP asset is not a directory: " + label + " (" + str(path) + ")")
    return path


def cli_memory_path(name: str) -> Path:
    """Resolve one of the legacy CLI readline history files."""

    if not name or Path(name).name != name or name in {".", ".."}:
        raise NIEPPathError("invalid CLI history file name: " + repr(name))
    # History files are created lazily by readline, so only the containing
    # directory must exist; unlike asset_path this must not require ``name``
    # to be present already.
    return asset_directory("CLI", "CLIMEM", description="CLI/CLIMEM") / name


__all__ = ["NIEPPathError", "asset_directory", "asset_path", "cli_memory_path", "repository_root"]
