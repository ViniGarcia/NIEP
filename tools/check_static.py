#!/usr/bin/env python3
"""Static validation checks for the NIEP Python 3 port.

The checks here intentionally avoid importing NIEP modules because some modules
open libvirt connections at import time. This script should run both on the host
and inside the Vagrant VM.
"""

from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PYTHON_PATHS = [
    ROOT / "CLI",
    ROOT / "TOPO-MAN",
    ROOT / "VEM",
    ROOT / "tests",
]

JSON_GLOBS = [
    "tutorial/examples/*.json",
    "tests/topologies/*.json",
    "EXAMPLES/**/*.json",
    "CONFS/*.json",
]

MARKDOWN_GLOBS = [
    "README.md",
    "tutorial/*.md",
]


def iter_python_files() -> list[Path]:
    files: list[Path] = []
    for base in PYTHON_PATHS:
        if base.exists():
            files.extend(sorted(base.rglob("*.py")))
    return files


def iter_json_files() -> list[Path]:
    files: list[Path] = []
    for pattern in JSON_GLOBS:
        files.extend(sorted(ROOT.glob(pattern)))
    return files


def iter_markdown_files() -> list[Path]:
    files: list[Path] = []
    for pattern in MARKDOWN_GLOBS:
        files.extend(sorted(ROOT.glob(pattern)))
    return files


def check_python_compile() -> list[str]:
    errors: list[str] = []
    for path in iter_python_files():
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            errors.append(f"{path.relative_to(ROOT)}: {exc.msg}")
    return errors


def check_json() -> list[str]:
    errors: list[str] = []
    for path in iter_json_files():
        try:
            with path.open(encoding="utf-8") as handle:
                json.load(handle)
        except Exception as exc:  # noqa: BLE001 - report exact file and parser error
            errors.append(f"{path.relative_to(ROOT)}: {exc}")
    return errors


def check_markdown_fences() -> list[str]:
    errors: list[str] = []
    for path in iter_markdown_files():
        fences = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("```"):
                fences += 1
        if fences % 2 != 0:
            errors.append(f"{path.relative_to(ROOT)}: unbalanced fenced code blocks")
    return errors


def check_required_tutorial_examples() -> list[str]:
    required = [
        "tutorial/examples/mininet-ping.json",
        "tutorial/examples/vm-basic.json",
        "tutorial/examples/vm-host-link.json",
        "tutorial/examples/click-forward-topology.json",
        "tutorial/examples/click/forward.click",
        "tutorial/examples/click/policy-forward.click",
    ]
    errors: list[str] = []
    for relpath in required:
        if not (ROOT / relpath).is_file():
            errors.append(f"{relpath}: missing required tutorial artifact")
    return errors


def main() -> int:
    checks = [
        ("python compile", check_python_compile),
        ("json syntax", check_json),
        ("markdown fences", check_markdown_fences),
        ("tutorial artifacts", check_required_tutorial_examples),
    ]

    failed = False
    for label, check in checks:
        errors = check()
        if errors:
            failed = True
            print(f"[FAIL] {label}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[ OK ] {label}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
