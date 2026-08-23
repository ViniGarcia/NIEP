import os
import select
import socket
import sys
import termios
import time
import tty
from contextlib import contextmanager

from niep.runtime.errors import RuntimeFailure


def socket_object(stream):
    return getattr(stream, "_sock", stream)


def receive(stream, size=65536):
    stream = socket_object(stream)
    if hasattr(stream, "recv"):
        return stream.recv(size)
    return stream.read(size)


def send(stream, data):
    stream = socket_object(stream)
    if hasattr(stream, "sendall"):
        stream.sendall(data)
    else:
        stream.write(data)
        if hasattr(stream, "flush"):
            stream.flush()


def _set_io_timeout(stream, remaining):
    setter = getattr(socket_object(stream), "settimeout", None)
    if setter is not None:
        setter(max(0.0, remaining))


class SocketTerminalSession:
    """Minimal injectable terminal stream lifecycle adapter.

    The stream itself is supplied by a runtime (for example Docker exec).  No
    socket is opened during construction or import.  Closing an already closed
    or absent stream is a successful, idempotent cleanup.
    """

    def __init__(self, stream=None, opener=None):
        self.stream = stream
        self._opener = opener

    def open_stream(self, *args, **kwargs):
        if self.stream is None:
            if self._opener is None:
                raise RuntimeFailure(
                    "open", "terminal", None, message="terminal stream opener is not configured"
                )
            try:
                self.stream = self._opener(*args, **kwargs)
            except RuntimeFailure:
                raise
            except Exception as exc:
                raise RuntimeFailure("open", "terminal", None, cause=exc, retryable=True) from exc
        return self.stream

    def close(self):
        if self.stream is None:
            return None
        stream, self.stream = self.stream, None
        try:
            shutdown = getattr(stream, "shutdown", None)
            if shutdown is not None:
                try:
                    shutdown(2)
                except OSError:
                    pass
            close = getattr(stream, "close", None)
            if close is not None:
                return close()
        except RuntimeFailure:
            raise
        except OSError as exc:
            raise RuntimeFailure("close", "terminal", None, cause=exc, retryable=True) from exc
        except Exception as exc:
            raise RuntimeFailure("close", "terminal", None, cause=exc, retryable=True) from exc
        return None


TerminalSessionAdapter = SocketTerminalSession
TerminalSessionRuntime = SocketTerminalSession


@contextmanager
def raw_terminal(file_descriptor):
    if not os.isatty(file_descriptor):
        yield
        return
    previous = termios.tcgetattr(file_descriptor)
    try:
        tty.setraw(file_descriptor)
        yield
    finally:
        termios.tcsetattr(file_descriptor, termios.TCSADRAIN, previous)


def bridge_terminal(stream, input_fd=None, output_fd=None, initial_output=b"", timeout=None):
    input_fd = sys.stdin.fileno() if input_fd is None else input_fd
    output_fd = sys.stdout.fileno() if output_fd is None else output_fd
    stream = socket_object(stream)
    deadline = None if timeout is None else time.monotonic() + timeout

    if initial_output:
        os.write(output_fd, initial_output)

    with raw_terminal(input_fd):
        input_open = True
        while True:
            sources = [stream]
            if input_open:
                sources.append(input_fd)
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            readable, _, _ = select.select(sources, [], [], remaining)
            if not readable:
                return
            if stream in readable:
                if remaining is not None:
                    _set_io_timeout(stream, remaining)
                try:
                    data = receive(stream)
                except (socket.timeout, TimeoutError):
                    return
                if not data:
                    break
                os.write(output_fd, data)
            if input_open and input_fd in readable:
                data = os.read(input_fd, 65536)
                if not data:
                    input_open = False
                    shutdown = getattr(stream, "shutdown", None)
                    if shutdown is not None:
                        try:
                            shutdown(1)
                        except OSError:
                            pass
                    continue
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return
                if remaining is not None:
                    _set_io_timeout(stream, remaining)
                try:
                    send(stream, data)
                except (socket.timeout, TimeoutError):
                    return


def bridge_sockets(client, stream, timeout=None):
    stream = socket_object(stream)
    peers = (client, stream)
    deadline = None if timeout is None else time.monotonic() + timeout
    while True:
        remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
        readable, _, _ = select.select(peers, [], [], remaining)
        if not readable:
            return False
        for source in readable:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            if remaining is not None:
                _set_io_timeout(source, remaining)
            try:
                data = receive(source)
            except (socket.timeout, TimeoutError):
                return False
            if not data:
                return True
            target = stream if source is client else client
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            if remaining is not None:
                _set_io_timeout(target, remaining)
            try:
                send(target, data)
            except (socket.timeout, TimeoutError):
                return False
