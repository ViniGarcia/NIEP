"""Versioned command protocol used by the local application interfaces.

The daemon, ``niepctl`` and the legacy command interpreter all use this
module as their boundary.  Runtime objects deliberately do not appear in the
DTOs: interactive resources are handled by the application facade through an
out-of-band stream instead.
"""

from __future__ import annotations

import json
import math
import shlex
import uuid
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


COMMAND_PROTOCOL = "niep.command"
COMMAND_VERSION = 1


class CommandProtocolError(ValueError):
    """Raised when a command envelope is not a supported protocol message."""

    def __init__(self, message: str, *, code: str = "invalid_request") -> None:
        super().__init__(message)
        self.code = code


def _freeze(value: Any) -> Any:
    """Return an immutable JSON-shaped value or reject runtime objects."""

    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise CommandProtocolError("command data cannot contain non-finite numbers")
        return value
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise CommandProtocolError("command object keys must be strings")
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    raise CommandProtocolError(
        "command data must contain only JSON-compatible values",
        code="invalid_request",
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value


def _validate_envelope(mapping: Mapping[str, Any], allowed: set[str]) -> None:
    if any(not isinstance(key, str) for key in mapping):
        raise CommandProtocolError("command envelope keys must be strings")
    unknown = set(mapping) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise CommandProtocolError("unknown command fields: " + names)


@dataclass(frozen=True, slots=True)
class CommandRequest:
    """Immutable protocol v1 command request.

    Missing protocol metadata is accepted when parsing a legacy request.  It
    is immediately normalized to v1, so every request entering the use-case
    layer has one unambiguous shape.
    """

    command: str
    args: tuple[str, ...] = ()
    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    protocol: str = COMMAND_PROTOCOL
    version: int = COMMAND_VERSION
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.protocol, str) or self.protocol != COMMAND_PROTOCOL:
            raise CommandProtocolError("unsupported command protocol")
        if type(self.version) is not int or self.version != COMMAND_VERSION:
            raise CommandProtocolError(
                "unsupported command protocol version: " + str(self.version),
                code="unsupported_version",
            )
        if not isinstance(self.command, str) or not self.command.strip():
            raise CommandProtocolError("command must be a non-empty string")
        if not isinstance(self.request_id, str) or not self.request_id.strip():
            raise CommandProtocolError("request_id must be a non-empty string")
        if not isinstance(self.args, (tuple, list)) or any(not isinstance(arg, str) for arg in self.args):
            raise CommandProtocolError("command args must be strings")
        if not isinstance(self.options, Mapping):
            raise CommandProtocolError("options must be a JSON object")
        object.__setattr__(self, "command", self.command.strip())
        object.__setattr__(self, "args", tuple(self.args))
        object.__setattr__(self, "options", _freeze(dict(self.options)))

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CommandRequest":
        if not isinstance(payload, Mapping):
            raise CommandProtocolError("command request must be a JSON object")
        _validate_envelope(
            payload,
            {"protocol", "version", "request_id", "command", "args", "options"},
        )
        protocol = payload.get("protocol", COMMAND_PROTOCOL)
        version = payload.get("version", COMMAND_VERSION)
        if not isinstance(protocol, str):
            raise CommandProtocolError("protocol must be a string")
        if type(version) is not int:
            raise CommandProtocolError("version must be an integer", code="unsupported_version")
        args = payload.get("args", ())
        if not isinstance(args, (list, tuple)):
            raise CommandProtocolError("args must be a JSON array")
        options = payload.get("options", {})
        if not isinstance(options, Mapping):
            raise CommandProtocolError("options must be a JSON object")
        request_id = uuid.uuid4().hex if "request_id" not in payload else payload["request_id"]
        return cls(
            protocol=protocol,
            version=version,
            request_id=request_id,
            command=payload.get("command", ""),
            args=tuple(args),
            options=options,
        )

    @classmethod
    def from_cli(cls, line: str, *, request_id: str | None = None) -> "CommandRequest":
        if not isinstance(line, str):
            raise CommandProtocolError("command line must be a string")
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            raise CommandProtocolError("invalid command quoting: " + str(exc)) from exc
        if not tokens:
            raise CommandProtocolError("command line is empty")
        return cls(tokens[0], tuple(tokens[1:]), request_id=request_id or uuid.uuid4().hex)

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol,
            "version": self.version,
            "request_id": self.request_id,
            "command": self.command,
            "args": list(self.args),
            "options": _thaw(self.options),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(frozen=True, slots=True)
class StreamDescriptor:
    """Safe metadata for an interactive stream, never the stream itself."""

    kind: str
    resource_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or not isinstance(self.resource_id, str):
            raise CommandProtocolError("stream descriptor fields must be strings")

    def to_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "resource_id": self.resource_id}


@dataclass(frozen=True, slots=True)
class CommandResponse:
    """Immutable, JSON-serializable response envelope."""

    request_id: str
    ok: bool
    code: str
    message: str = ""
    data: Any = None
    status: int | None = None
    detail: str = ""
    exit_code: int = 0
    stream: StreamDescriptor | None = field(default=None, repr=False, compare=False)
    protocol: str = COMMAND_PROTOCOL
    version: int = COMMAND_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.protocol, str) or self.protocol != COMMAND_PROTOCOL:
            raise CommandProtocolError("unsupported command protocol")
        if type(self.version) is not int or self.version != COMMAND_VERSION:
            raise CommandProtocolError("unsupported command protocol version")
        if not isinstance(self.request_id, str) or not self.request_id:
            raise CommandProtocolError("response request_id must be a non-empty string")
        if type(self.ok) is not bool:
            raise CommandProtocolError("response ok must be boolean")
        if not isinstance(self.code, str) or not self.code:
            raise CommandProtocolError("response code must be a non-empty string")
        if not isinstance(self.message, str) or not isinstance(self.detail, str):
            raise CommandProtocolError("response messages must be strings")
        if self.status is not None and type(self.status) is not int:
            raise CommandProtocolError("response status must be an integer")
        if type(self.exit_code) is not int:
            raise CommandProtocolError("response exit_code must be an integer")
        if self.stream is not None and not isinstance(self.stream, StreamDescriptor):
            raise CommandProtocolError("response stream must be a StreamDescriptor")
        if self.data is not None:
            object.__setattr__(self, "data", _freeze(self.data))

    @classmethod
    def from_result(cls, request: CommandRequest, result: Any) -> "CommandResponse":
        code = result.code.value if hasattr(result.code, "value") else str(result.code)
        ok = bool(result.ok)
        status = getattr(result, "status", None)
        exit_code = status if code == "container_exec" and isinstance(status, int) else (0 if ok else 1)
        data = getattr(result, "data", None)
        stream = None
        # ``open_stream`` returns a descriptor only.  A raw stream is an
        # application-internal compatibility result and is never serialized.
        if code == "container_shell" and data is not None:
            data = None
        return cls(
            request_id=request.request_id,
            ok=ok,
            code=code,
            message=str(getattr(result, "message", "") or ""),
            data=data,
            status=status,
            detail=str(getattr(result, "detail", "") or ""),
            exit_code=exit_code,
            stream=stream,
        )

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "CommandResponse":
        if not isinstance(payload, Mapping):
            raise CommandProtocolError("command response must be a JSON object")
        _validate_envelope(
            payload,
            {
                "protocol",
                "version",
                "request_id",
                "ok",
                "code",
                "message",
                "data",
                "status",
                "detail",
                "exit_code",
                "stream",
            },
        )
        protocol = payload.get("protocol", COMMAND_PROTOCOL)
        version = payload.get("version", COMMAND_VERSION)
        if not isinstance(protocol, str) or type(version) is not int:
            raise CommandProtocolError("invalid response protocol metadata")
        if type(payload.get("ok")) is not bool:
            raise CommandProtocolError("response ok must be boolean")
        stream = payload.get("stream")
        if stream is not None:
            if not isinstance(stream, Mapping) or set(stream) != {"kind", "resource_id"}:
                raise CommandProtocolError("invalid response stream descriptor")
            stream = StreamDescriptor(kind=stream["kind"], resource_id=stream["resource_id"])
        return cls(
            protocol=protocol,
            version=version,
            request_id=payload.get("request_id", ""),
            ok=payload["ok"],
            code=payload.get("code", ""),
            message=payload.get("message", ""),
            data=payload.get("data"),
            status=payload.get("status"),
            detail=payload.get("detail", ""),
            exit_code=payload.get("exit_code", 0),
            stream=stream,
        )

    @classmethod
    def failure(cls, request_id: str, code: str, message: str, *, detail: str = "") -> "CommandResponse":
        return cls(
            request_id=request_id,
            ok=False,
            code=code,
            message=message,
            detail=detail,
            exit_code=1,
        )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "protocol": self.protocol,
            "version": self.version,
            "request_id": self.request_id,
            "ok": self.ok,
            "code": self.code,
            "message": self.message,
            "exit_code": self.exit_code,
        }
        if self.data is not None:
            payload["data"] = _thaw(self.data)
        if self.status is not None:
            payload["status"] = self.status
        if self.detail:
            payload["detail"] = self.detail
        if self.stream is not None:
            payload["stream"] = self.stream.to_dict()
        return payload

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def to_service_result(self) -> Any:
        # Import lazily to keep the protocol DTO usable without runtime
        # adapters and to avoid a domain -> application import cycle.
        from niep.domain.result import ResultCode, ServiceResult

        try:
            result_code: Any = ResultCode(self.code)
        except ValueError:
            result_code = self.code
        return ServiceResult(
            ok=self.ok,
            code=result_code,
            message=self.message,
            data=_thaw(self.data) if self.data is not None else None,
            status=self.status,
            detail=self.detail,
        )


__all__ = [
    "COMMAND_PROTOCOL",
    "COMMAND_VERSION",
    "PROTOCOL",
    "VERSION",
    "CommandProtocolError",
    "CommandRequest",
    "CommandResponse",
    "StreamDescriptor",
]

# Short aliases make the protocol boundary discoverable for integrations that
# do not need the more descriptive constant names.
PROTOCOL = COMMAND_PROTOCOL
VERSION = COMMAND_VERSION
