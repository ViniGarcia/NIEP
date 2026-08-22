"""Neutral topology diagnostics and document value objects.

This module deliberately contains no optional runtime imports.  It is safe to
use from tooling which only wants to inspect a topology definition.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping


@dataclass(frozen=True)
class ValidationIssue:
    """One schema or cross-reference diagnostic.

    ``code`` is intentionally allowed to be either an integer (the historical
    parser status) or a string (new callers may use a stable symbolic code).
    Keeping both forms lets the application preserve the old CLI wire codes.
    """

    code: int | str
    message: str
    field: str | None = None
    file: str | None = None
    line: int | None = None
    value: Any = None

    @property
    def status(self):
        return self.code

    @property
    def path(self):
        return self.field

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "field": self.field,
            "file": self.file,
            "line": self.line,
            "value": self.value,
        }
        return result

    def __str__(self) -> str:
        parts = [self.message]
        if self.field is not None:
            parts.append(f"field={self.field}")
        if self.value is not None:
            parts.append(f"value={self.value!r}")
        if self.file is not None:
            location = self.file
            if self.line is not None:
                location += f":{self.line}"
            parts.append(f"file={location}")
        return "; ".join(parts)


@dataclass(frozen=True)
class ValidationResult:
    """An immutable aggregate of validation issues and an optional value."""

    value: Any = None
    issues: tuple[ValidationIssue, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "issues", tuple(self.issues or ()))

    @property
    def ok(self) -> bool:
        return not self.issues

    @property
    def valid(self) -> bool:
        return self.ok

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return self.issues

    @property
    def status(self) -> int | str | None:
        return self.issues[0].code if self.issues else 0

    @property
    def code(self) -> int | str | None:
        return self.status

    @property
    def first_issue(self) -> ValidationIssue | None:
        return self.issues[0] if self.issues else None

    @classmethod
    def success(cls, value: Any = None) -> "ValidationResult":
        return cls(value=value)

    @classmethod
    def failure(
        cls,
        issue: ValidationIssue | Iterable[ValidationIssue],
        value: Any = None,
    ) -> "ValidationResult":
        if isinstance(issue, ValidationIssue):
            issue = (issue,)
        return cls(value=value, issues=tuple(issue))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "status": self.status,
            "issues": [issue.to_dict() for issue in self.issues],
            "value": self.value,
        }

    def detail(self) -> str:
        return " | ".join(str(issue) for issue in self.issues)

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class DescriptorDocument:
    """A JSON descriptor and the file which declared it."""

    path: str
    data: Mapping[str, Any]
    field: str | None = None
    line: int | None = None

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


@dataclass(frozen=True)
class TopologyDocument:
    """Loaded topology JSON plus nested descriptors resolved by the loader."""

    path: str
    data: Mapping[str, Any]
    descriptors: Mapping[str, tuple[DescriptorDocument, ...]]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    @property
    def ok(self) -> bool:
        return True

    @property
    def valid(self) -> bool:
        return True

    @property
    def value(self) -> "TopologyDocument":
        return self
