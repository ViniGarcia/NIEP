#!/usr/bin/env python3
"""Validate the evidence file used before making privileged CI required.

The repository starts with an empty history.  GitHub Actions run history and
the uploaded diagnostics are the source of truth; successful run IDs are
copied into the small JSON ledger only after reviewing those artifacts.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

REQUIRED_RUN_FIELDS = frozenset({"id", "revision", "scenario", "status"})
ALLOWED_STATUSES = frozenset({"success", "failure", "failed", "cancelled", "skipped"})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", type=Path, required=True)
    parser.add_argument(
        "--minimum",
        type=int,
        help="override the minimum from the history file (useful for local checks)",
    )
    parser.add_argument(
        "--enforce",
        action="store_true",
        help="fail when the minimum successful, distinct runs are not recorded",
    )
    return parser.parse_args()


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate_payload(
    payload: object, minimum_override: int | None = None
) -> tuple[list[str], set[str], int | None]:
    """Validate the ledger and return errors, successful IDs and the minimum.

    Validation is deliberately strict.  A malformed entry must not silently
    disappear from the flakiness count: the history is evidence used for a
    branch-protection decision, so every row needs an identity, revision,
    scenario and known status.
    """

    errors: list[str] = []
    successful_ids: set[str] = set()
    if not isinstance(payload, dict):
        return ["history root must be an object"], successful_ids, None

    runs = payload.get("runs")
    if not isinstance(runs, list):
        errors.append("history field 'runs' must be a list")

    minimum = minimum_override if minimum_override is not None else payload.get("required_runs", 10)
    if type(minimum) is not int or minimum < 1:  # bool is intentionally not an integer here.
        errors.append("history minimum must be a positive integer")
        minimum_value: int | None = None
    else:
        minimum_value = minimum

    seen_ids: set[str] = set()
    if not isinstance(runs, list):
        return errors, successful_ids, minimum_value

    for index, run in enumerate(runs):
        prefix = f"runs[{index}]"
        if not isinstance(run, dict):
            errors.append(f"{prefix} must be an object")
            continue

        missing = sorted(REQUIRED_RUN_FIELDS - run.keys())
        if missing:
            errors.append(f"{prefix} missing required fields: {', '.join(missing)}")

        for field in sorted(REQUIRED_RUN_FIELDS & run.keys()):
            value = run[field]
            if not _non_empty_string(value):
                errors.append(f"{prefix}.{field} must be a non-empty string")

        status = run.get("status")
        if isinstance(status, str) and status not in ALLOWED_STATUSES:
            errors.append(f"{prefix}.status must be one of: {', '.join(sorted(ALLOWED_STATUSES))}")

        run_id = run.get("id")
        if _non_empty_string(run_id):
            if run_id in seen_ids:
                errors.append(f"{prefix}.id duplicates another run ID: {run_id}")
            seen_ids.add(run_id)
            if status == "success":
                successful_ids.add(run_id)

    return errors, successful_ids, minimum_value


def main() -> int:
    args = parse_args()
    try:
        payload = json.loads(args.history.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"[FAIL] invalid privileged CI history: {exc}")
        return 1

    errors, successful_ids, minimum = validate_payload(payload, args.minimum)
    if errors:
        print("[FAIL] invalid privileged CI history")
        for error in errors:
            print(f"  - {error}")
        return 1
    assert minimum is not None
    count = len(successful_ids)
    print(f"[INFO] privileged CI history: {count}/{minimum} successful distinct runs")
    if count < minimum:
        print("[INFO] keep privileged jobs informational until the evidence gate is met")
        return 1 if args.enforce else 0
    print("[ OK ] privileged CI promotion criterion met")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
