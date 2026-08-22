#!/usr/bin/env python3
"""Run the intentionally small host lint/format gate.

The repository contains a vendored POX tree which is maintained upstream and
is not part of the NIEP style gate.  Keep the file list explicit so a change
to a large vendored tree (or an LFS object) cannot make pull-request CI
expensive or unexpectedly fail.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MAINTAINED_DIRS = ("niep", "CLI", "TOPO-MAN", "VEM", "tools", "tests")
RUFF_SAFE_RULES = ("E9", "F63", "F7", "F82")


def maintained_files() -> list[Path]:
    files: list[Path] = []
    for directory in MAINTAINED_DIRS:
        base = ROOT / directory
        if base.exists():
            files.extend(sorted(base.rglob("*.py")))
    return files


def check_whitespace(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in files:
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{path.relative_to(ROOT)}: not UTF-8 ({exc})")
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            if line.rstrip("\n\r").endswith((" ", "\t")):
                errors.append(f"{path.relative_to(ROOT)}:{line_number}: trailing whitespace")
        if content and not content.endswith("\n"):
            errors.append(f"{path.relative_to(ROOT)}: missing final newline")
    return errors


def run_ruff(files: list[Path]) -> int:
    command = [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "--select",
        ",".join(RUFF_SAFE_RULES),
        "--exclude",
        "OFCONTROLLERS/pox",
        *(str(path.relative_to(ROOT)) for path in files),
    ]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print("[FAIL] ruff safety lint")
    else:
        print("[ OK ] ruff safety lint (POX excluded)")
    return result.returncode


def run_format_check() -> int:
    # Formatting is enforced for CI-owned tooling.  Existing application code
    # is checked for safe syntax/lint rules above and can be migrated gradually
    # without reformatting a whole legacy tree in this task.
    command = [sys.executable, "-m", "ruff", "format", "--check", "tools/ci"]
    result = subprocess.run(command, cwd=ROOT, check=False)
    if result.returncode:
        print("[FAIL] ruff format check for tools/ci")
    else:
        print("[ OK ] ruff format check for tools/ci")
    return result.returncode


def main() -> int:
    files = maintained_files()
    errors = check_whitespace(files)
    for error in errors:
        print(f"[FAIL] {error}")
    if not errors:
        print("[ OK ] whitespace and UTF-8")

    status = len(errors)
    status += run_ruff(files)
    status += run_format_check()
    return 1 if status else 0


if __name__ == "__main__":
    raise SystemExit(main())
