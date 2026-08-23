"""Compatibility import location for the local ``niep.command`` protocol."""

from .commands import (
    COMMAND_PROTOCOL,
    COMMAND_VERSION,
    PROTOCOL,
    VERSION,
    CommandProtocolError,
    CommandRequest,
    CommandResponse,
    StreamDescriptor,
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
