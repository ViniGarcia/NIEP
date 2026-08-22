#!/usr/bin/env python3
"""Validate local Markdown links and paths used by documented examples.

Network links are deliberately not fetched: a documentation gate must be
deterministic and should not turn a temporary outage of an external site into
a failed pull request.  Local links and repository example paths are checked
against the checkout instead.
"""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[2]
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")
EXAMPLE_PATH = re.compile(
    r"(?<![A-Za-z0-9_./-])((?:tutorial/examples|tests/(?:fixtures|topologies))/[A-Za-z0-9_./-]+)"
)
MARKDOWN_GLOBS = (
    "*.md",
    "docs/**/*.md",
    "tutorial/**/*.md",
    "INSTALLATION/**/*.md",
    "plano-refatoracao/**/*.md",
)


def markdown_files() -> list[Path]:
    paths: set[Path] = set()
    for pattern in MARKDOWN_GLOBS:
        paths.update(ROOT.glob(pattern))
    return sorted(path for path in paths if path.is_file())


def split_target(raw_target: str) -> tuple[str, str]:
    target = raw_target.strip()
    # Markdown permits an optional title after a URL.  Repository paths in
    # this project never contain spaces, so taking the first token is safe and
    # avoids treating a title as part of the path.
    if " " in target:
        target = target.split(maxsplit=1)[0]
    if target.startswith("<") and target.endswith(">"):  # inline Markdown URL
        target = target[1:-1]
    path, separator, fragment = target.partition("#")
    return unquote(path), fragment if separator else ""


def is_external(path: str) -> bool:
    return path.startswith(("https://", "http://", "mailto:", "tel:"))


def check_links(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        for line_number, line in enumerate(
            source.read_text(encoding="utf-8").splitlines(), start=1
        ):
            for match in MARKDOWN_LINK.finditer(line):
                path, fragment = split_target(match.group(1))
                if is_external(path):
                    continue
                if not path and not fragment:
                    continue
                target = (
                    source.resolve()
                    if not path
                    else (
                        (source.parent / path).resolve() if not path.startswith("/") else Path(path)
                    )
                )
                try:
                    target.relative_to(ROOT)
                except ValueError:
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: link escapes repository: {path}"
                    )
                    continue
                if not target.exists():
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing link target: {path}"
                    )
                    continue
                if fragment and target.is_file() and not has_fragment(target, fragment):
                    target_label = path or str(source.relative_to(ROOT))
                    errors.append(
                        f"{source.relative_to(ROOT)}:{line_number}: missing anchor #{fragment} in {target_label}"
                    )
    return errors


def github_slug(heading: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", heading.lower())
    return re.sub(r"\s+", "-", slug).strip("-")


def has_fragment(path: Path, fragment: str) -> bool:
    wanted = github_slug(unquote(fragment))
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
            if github_slug(heading) == wanted:
                return True
    return False


def check_examples(files: list[Path]) -> list[str]:
    errors: list[str] = []
    for source in files:
        text = source.read_text(encoding="utf-8")
        for match in EXAMPLE_PATH.finditer(text):
            path = ROOT / match.group(1).rstrip("`'\")],.;:")
            if not path.is_file():
                errors.append(
                    f"{source.relative_to(ROOT)}: missing documented example: {match.group(1)}"
                )
    return errors


def main() -> int:
    files = markdown_files()
    errors = check_links(files) + check_examples(files)
    if errors:
        print("[FAIL] documentation links/examples")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"[ OK ] documentation links/examples ({len(files)} Markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
