"""JSON and path loading for topology definitions.

The loader performs file IO only. It never imports an optional runtime and it
resolves every relative reference against the descriptor that contains it.
"""

from __future__ import annotations

import json
from copy import deepcopy
from os.path import abspath, dirname, isfile, isabs, join, normpath
from typing import Any

from niep.domain.topology import DescriptorDocument, TopologyDocument, ValidationIssue, ValidationResult


def resolve_path(value: str, descriptor: str) -> str:
    """Resolve ``value`` relative to the descriptor which declared it."""

    if not isinstance(value, str):
        return value
    if isabs(value):
        return normpath(value)
    return normpath(abspath(join(dirname(abspath(descriptor)), value)))


class PathResolver:
    """Stateless path resolver; no process cwd or global base directory state."""

    def resolve(self, value: str, descriptor: str) -> str:
        return resolve_path(value, descriptor)


class TopologyLoader:
    """Load a topology and its direct descriptor files into neutral documents."""

    SECTION_CODES = {"VMS": -3, "VNFS": -3, "CONTAINERS": -3, "SFCS": -5}
    SECTION_MISSING_CODES = {"VMS": -2, "VNFS": -2, "CONTAINERS": -2, "SFCS": -4}

    def __init__(self, resolver: PathResolver | None = None):
        self.resolver = resolver or PathResolver()
        self.last_result: ValidationResult | None = None

    def resolve_path(self, value: str, descriptor: str) -> str:
        return self.resolver.resolve(value, descriptor)

    def _issue(self, code, message, *, field=None, file=None, line=None, value=None):
        return ValidationIssue(code, message, field=field, file=file, line=line, value=value)

    def load_descriptor(self, path: str, *, field: str | None = None, code: int = -3,
                        missing_code: int | None = None) -> DescriptorDocument | None:
        path = abspath(path)
        if not isfile(path):
            self._pending_issues.append(self._issue(
                missing_code if missing_code is not None else code,
                "Descriptor file does not exist", field=field, file=path,
            ))
            return None
        try:
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
        except json.JSONDecodeError as exc:
            self._pending_issues.append(self._issue(
                code,
                f"Invalid JSON syntax at line {exc.lineno}, column {exc.colno}: {exc.msg}",
                field=field, file=path, line=exc.lineno,
            ))
            return None
        except OSError as exc:
            self._pending_issues.append(self._issue(
                code, f"Could not read descriptor file: {exc}", field=field, file=path,
            ))
            return None
        if not isinstance(data, dict):
            self._pending_issues.append(self._issue(
                code, "Descriptor root must be a JSON object", field=field, file=path,
                value=data,
            ))
            return None
        return DescriptorDocument(path=path, data=deepcopy(data), field=field)

    def load_result(self, path: str) -> ValidationResult:
        self._pending_issues: list[ValidationIssue] = []
        source = abspath(str(path))
        if not isfile(source):
            result = ValidationResult.failure(self._issue(-1, "Topology file does not exist", file=source))
            self.last_result = result
            return result
        try:
            with open(source, encoding="utf-8") as stream:
                root = json.load(stream)
        except json.JSONDecodeError as exc:
            issue = self._issue(
                -1,
                f"Invalid JSON syntax at line {exc.lineno}, column {exc.colno}: {exc.msg}",
                file=source, line=exc.lineno,
            )
            result = ValidationResult.failure(issue)
            self.last_result = result
            return result
        except OSError as exc:
            result = ValidationResult.failure(self._issue(-1, f"Could not read topology file: {exc}", file=source))
            self.last_result = result
            return result
        if not isinstance(root, dict):
            result = ValidationResult.failure(self._issue(-2, "Topology root must be a JSON object", field="$", file=source, value=root))
            self.last_result = result
            return result

        data = deepcopy(root)
        descriptors: dict[str, tuple[DescriptorDocument, ...]] = {}
        for section in ("VMS", "VNFS", "SFCS", "CONTAINERS"):
            references = data.get(section, [])
            if not isinstance(references, list):
                continue
            loaded: list[DescriptorDocument] = []
            for index, reference in enumerate(references):
                field = f"{section}[{index}]"
                if not isinstance(reference, str):
                    self._pending_issues.append(self._issue(
                        self.SECTION_MISSING_CODES[section],
                        f"{section[:-1] if section != 'SFCS' else 'SFC'} descriptor path must be a string",
                        field=field, file=source, value=reference,
                    ))
                    loaded.append(None)
                    continue
                descriptor_path = self.resolve_path(reference, source)
                descriptor = self.load_descriptor(
                    descriptor_path,
                    field=field,
                    code=self.SECTION_CODES[section],
                    missing_code=self.SECTION_MISSING_CODES[section],
                )
                loaded.append(descriptor)
            descriptors[section] = tuple(loaded)

        document = TopologyDocument(path=source, data=data, descriptors=descriptors)
        result = ValidationResult(value=document, issues=tuple(self._pending_issues))
        self.last_result = result
        return result

    def load(self, path: str) -> TopologyDocument | None:
        """Return a document, retaining diagnostics in ``last_result``."""

        result = self.load_result(path)
        return result.value if result.ok else None

    load_document = load

    read = load
