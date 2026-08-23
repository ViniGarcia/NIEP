"""Narrow application stream ports for interactive compatibility clients."""

from __future__ import annotations

from typing import Any


def bridge_terminal(stream: Any, *, initial_output: bytes = b"") -> Any:
    from niep.runtime.terminal_session import bridge_terminal as runtime_bridge_terminal

    return runtime_bridge_terminal(stream, initial_output=initial_output)


def bridge_sockets(connection: Any, stream: Any) -> Any:
    from niep.runtime.terminal_session import bridge_sockets as runtime_bridge_sockets

    return runtime_bridge_sockets(connection, stream)


__all__ = ["bridge_sockets", "bridge_terminal"]
