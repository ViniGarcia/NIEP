"""Errors shared by runtime adapters.

Runtime failures deliberately keep the original exception in ``cause`` while
exposing a small, JSON-safe representation for the application boundary.  A
cause is never serialized directly: SDK exceptions frequently contain request
objects, sockets, or credentials that are neither serializable nor safe to
return to a client.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from subprocess import CalledProcessError
from typing import Any


def _safe_value(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded JSON-compatible value without invoking arbitrary reprs."""

    if depth > 4:
        return "<truncated>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= 2048 else value[:2048] + "..."
    if isinstance(value, bytes):
        # Runtime command output is often bytes; preserve useful diagnostics
        # without putting arbitrary binary data in an API response.
        return value[:2048].decode("utf-8", "replace")
    if isinstance(value, Mapping):
        return {
            str(key): "<redacted>"
            if any(marker in str(key).lower() for marker in ("password", "passwd", "secret", "token", "authorization"))
            else _safe_value(item, depth=depth + 1)
            for key, item in list(value.items())[:100]
        }
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_safe_value(item, depth=depth + 1) for item in list(value)[:100]]
    # Do not call repr(value): it may expose object internals or secrets.
    return {"type": type(value).__name__}


def safe_context(context: Mapping[str, Any] | None = None, **values: Any) -> dict[str, Any]:
    """Copy context to a bounded, JSON-safe mapping.

    This helper is intentionally public so adapters can use the same behavior
    when adding command, status, or SDK metadata to a failure.
    """

    merged: dict[str, Any] = {}
    if context:
        merged.update(context)
    merged.update(values)
    return _safe_value(merged)


def _safe_command(command: Any) -> Any:
    """Copy a command while masking common credential argument forms."""

    if not isinstance(command, Sequence) or isinstance(command, (str, bytes, bytearray)):
        return command
    masked = []
    redact_next = False
    secret_flags = {"-p", "--password", "--passwd", "--secret", "--token"}
    for item in command:
        text = str(item)
        if redact_next:
            masked.append("<redacted>")
            redact_next = False
            continue
        if text.lower() in secret_flags:
            masked.append(text)
            redact_next = True
            continue
        if any(text.lower().startswith(flag + "=") for flag in secret_flags):
            masked.append(text.split("=", 1)[0] + "=<redacted>")
            continue
        masked.append(item)
    return masked


def command_failure(
    operation: str,
    resource_type: str | None,
    resource_id: Any,
    command: Any,
    cause: BaseException,
    *,
    retryable: bool | None = None,
    context: Mapping[str, Any] | None = None,
    message: str | None = None,
) -> "RuntimeFailure":
    """Build a safe failure for a command adapter boundary.

    ``subprocess`` exceptions carry command/output objects that should not be
    exposed directly by API or cleanup payloads.  Adapters call this helper
    only after preserving an existing :class:`RuntimeFailure` identity.  A
    failed command (``CalledProcessError``) is a completed operation and is
    therefore not retryable by default; an ``OSError`` usually means the
    command could not be started and can be retried.
    """

    details = dict(context or {})
    details.setdefault("command", _safe_command(command))
    returncode = getattr(cause, "returncode", None)
    if returncode is not None:
        details.setdefault("returncode", returncode)
    output = getattr(cause, "output", None)
    if output is not None:
        details.setdefault("output", output)
    stderr = getattr(cause, "stderr", None)
    if stderr is not None:
        details.setdefault("stderr", stderr)
    if retryable is None:
        retryable = not isinstance(cause, CalledProcessError)
    return RuntimeFailure(
        operation,
        resource_type,
        resource_id,
        cause=cause,
        retryable=retryable,
        context=details,
        message=message or "command failed",
    )


def cleanup_failure_record(
    error: Any,
    *,
    resource_type: str,
    resource_id: Any,
    operation: str,
) -> dict[str, Any]:
    """Return one JSON-safe cleanup record without flattening typed errors."""

    if isinstance(error, RuntimeFailure):
        record = error.to_dict()
    elif isinstance(error, Mapping):
        # Runtime boundaries may receive already serialized records from a
        # child adapter.  Copy the complete stable schema instead of
        # converting it to a message and losing cause/context metadata.
        record = {
            "operation": str(error.get("operation", operation)),
            "resource_type": error.get("resource_type", resource_type),
            "resource_id": error.get("resource_id", resource_id),
            "message": str(error.get("message", error)),
            "retryable": bool(error.get("retryable", False)),
            "context": safe_context(
                error.get("context") if isinstance(error.get("context"), Mapping) else None
            ),
            "cause": None,
        }
        cause = error.get("cause")
        if isinstance(cause, Mapping):
            record["cause"] = safe_context(cause)
        elif isinstance(cause, BaseException):
            cause_info = CauseInfo.from_exception(cause)
            record["cause"] = cause_info.to_dict() if cause_info is not None else None
        elif cause is not None:
            record["cause"] = {"type": type(cause).__name__, "message": str(cause)[:2048]}
        if "failure" in error:
            record["failure"] = safe_context({"failure": error["failure"]})["failure"]
    else:
        if not isinstance(error, BaseException):
            error = RuntimeError(str(error))
        record = RuntimeFailure(
            operation,
            resource_type,
            resource_id,
            cause=error,
        ).to_dict()
    if record.get("resource_type") is None:
        record["resource_type"] = str(resource_type)
    else:
        record["resource_type"] = str(record["resource_type"])
    if record.get("resource_id") is None:
        record["resource_id"] = str(_safe_value(resource_id))
    else:
        record["resource_id"] = str(_safe_value(record["resource_id"]))
    if not record.get("operation"):
        record["operation"] = str(operation)
    # Keep a stable schema even for a legacy exception adapter.
    record.setdefault("cause", None)
    record.setdefault("context", {})
    record.setdefault("retryable", False)
    return record


@dataclass(frozen=True)
class CauseInfo:
    """Safe summary of an exception cause."""

    type: str
    message: str

    @classmethod
    def from_exception(cls, cause: BaseException | None) -> "CauseInfo | None":
        if cause is None:
            return None
        message = str(cause)
        if len(message) > 2048:
            message = message[:2048] + "..."
        return cls(type=type(cause).__name__, message=message)

    def to_dict(self) -> dict[str, str]:
        return {"type": self.type, "message": self.message}


class RuntimeFailure(RuntimeError):
    """A typed failure at the application/infra boundary.

    ``operation`` identifies the capability being attempted, while
    ``resource_type`` and ``resource_id`` identify the affected resource.
    ``retryable`` is an explicit adapter decision and never inferred from the
    exception text.  ``cause`` remains available for logging and exception
    chaining; use :meth:`to_dict` for transport or persistence.
    """

    def __init__(
        self,
        operation: str,
        resource_type: str | None = None,
        resource_id: Any = None,
        cause: BaseException | str | None = None,
        retryable: bool = False,
        context: Mapping[str, Any] | None = None,
        *,
        message: str | None = None,
        type_: str | None = None,
        id: Any = None,
        **aliases: Any,
    ) -> None:
        # ``type`` was the original public keyword.  Accept it through
        # ``**aliases`` so the built-in ``type`` remains usable below.
        type_alias = aliases.pop("type", None)
        if aliases:
            unexpected = next(iter(aliases))
            raise TypeError("unexpected RuntimeFailure keyword: " + str(unexpected))
        if resource_type is None and type_ is not None:
            resource_type = type_
        if resource_type is None and type_alias is not None:
            resource_type = type_alias
        if resource_id is None and id is not None:
            resource_id = id
        self.operation = str(operation)
        self.resource_type = str(resource_type) if resource_type is not None else None
        self.resource_id = resource_id
        self.cause = cause
        self.retryable = bool(retryable)
        self.context = safe_context(context)
        if isinstance(cause, BaseException):
            # Preserve the causal chain even when callers construct and raise
            # the failure without an explicit ``raise ... from`` clause.
            self.__cause__ = cause

        if isinstance(cause, BaseException):
            self.message = message or str(cause) or type(cause).__name__
        elif cause is not None:
            self.message = message or str(cause)
        else:
            self.message = message or "runtime operation failed"
        super().__init__(self._format_message())

    def _format_message(self) -> str:
        parts = [self.message, "operation=" + self.operation]
        if self.resource_type is not None:
            parts.append("resource_type=" + self.resource_type)
        if self.resource_id is not None:
            parts.append("resource_id=" + str(self.resource_id))
        return "; ".join(parts)

    @property
    def cause_info(self) -> CauseInfo | None:
        if isinstance(self.cause, BaseException):
            return CauseInfo.from_exception(self.cause)
        if self.cause is not None:
            return CauseInfo(type=type(self.cause).__name__, message=str(self.cause)[:2048])
        return None

    @property
    def type(self) -> str | None:
        """Short alias used by callers that call the resource kind ``type``."""

        return self.resource_type

    @property
    def id(self) -> Any:
        return self.resource_id

    def to_dict(self) -> dict[str, Any]:
        """Serialize without leaking arbitrary exception/context objects."""

        result: dict[str, Any] = {
            "operation": self.operation,
            "resource_type": self.resource_type,
            "resource_id": _safe_value(self.resource_id),
            "retryable": self.retryable,
            "message": self.message,
            "context": _safe_value(self.context),
        }
        cause = self.cause_info
        result["cause"] = cause.to_dict() if cause is not None else None
        return result

    as_dict = to_dict


def raise_for_status(
    status: Any,
    *,
    operation: str,
    resource_type: str | None = None,
    resource_id: Any = None,
) -> Any:
    """Translate legacy non-zero status returns at an adapter edge.

    Existing callers still receive their historical zero/``None`` success
    value.  A non-zero integer is a typed failure instead of being interpreted
    by application code as an opaque error string.
    """

    successful = status is None or status is True or (isinstance(status, int) and not isinstance(status, bool) and status == 0)
    if not successful:
        if isinstance(status, int):
            raise RuntimeFailure(
                operation,
                resource_type,
                resource_id,
                message="runtime returned status " + str(status),
                context={"legacy_status": status},
            )
        raise RuntimeFailure(
            operation,
            resource_type,
            resource_id,
            message="runtime returned an unsuccessful result",
            context={"legacy_result": status},
        )
    return status


__all__ = [
    "CauseInfo",
    "RuntimeFailure",
    "cleanup_failure_record",
    "command_failure",
    "raise_for_status",
    "safe_context",
]
