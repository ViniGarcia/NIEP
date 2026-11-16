"""Hardened local command socket.

The socket is a privileged boundary.  This module deliberately owns the
Linux peer-credential check, the byte framing rules and the lifecycle of
interactive sessions.  The command dispatcher remains an application port;
no runtime object is exposed by this interface.
"""

from __future__ import annotations

import errno
import grp
import inspect
import json
import logging
import math
import os
from pathlib import Path
import socket
import stat
import struct
import sys
import threading
import time
from dataclasses import dataclass, replace
from numbers import Real
from typing import Any, Callable, Mapping, Protocol

from niep.application.command import CommandDispatcher, _public_result
from niep.application.commands import CommandProtocolError, CommandRequest, CommandResponse
from niep.application.stream import bridge_sockets
from niep.interfaces.protocol_limits import MAX_REQUEST_BYTES, MAX_RESPONSE_BYTES


SOCKET_GROUP = "niep"
SOCKET_MODE = 0o660
MIN_RESPONSE_BYTES = 192
_PEER_CREDENTIALS = struct.Struct("3i")


class PeerCredentialsError(RuntimeError):
    """Raised when Linux cannot provide trustworthy peer credentials."""


class UnauthorizedPeer(PermissionError):
    """Raised when a peer is not root and is not in the configured group."""


class SocketProtocolError(CommandProtocolError):
    """Protocol error produced by the byte-stream boundary."""

    def __init__(self, message: str, *, code: str = "invalid_request", request_id: str = "invalid"):
        super().__init__(message, code=code)
        self.request_id = request_id if isinstance(request_id, str) and request_id else "invalid"


@dataclass(frozen=True, slots=True)
class PeerCredentials:
    """Credentials obtained from the kernel for one connected peer."""

    pid: int
    uid: int
    gid: int
    supplementary_groups: tuple[int, ...] = ()
    supplementary_verified: bool = True

    @property
    def groups(self) -> tuple[int, ...]:
        """Compatibility alias used by policy and test providers."""

        return self.supplementary_groups


class PeerCredentialsProvider(Protocol):
    def get_peer_credentials(self, connection: Any) -> PeerCredentials: ...


class LinuxPeerCredentialsProvider:
    """Read immutable peer credentials from a Linux Unix stream socket.

    ``SO_PEERCRED`` supplies pid/uid/gid.  Supplementary groups are read from
    the Linux ``SO_PEERGROUPS`` socket option.  If the kernel does not expose
    that option, supplementary membership is deliberately unverified and can
    never grant access; the primary GID and uid=0 rules remain explicit.
    """

    def get_peer_credentials(self, connection: Any) -> PeerCredentials:
        if not sys_is_linux():
            raise PeerCredentialsError("NIEP socket authentication requires Linux")
        getsockopt = getattr(connection, "getsockopt", None)
        if getsockopt is None or not hasattr(socket, "SO_PEERCRED"):
            raise PeerCredentialsError("SO_PEERCRED is unavailable")
        try:
            raw = getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER_CREDENTIALS.size)
            pid, uid, gid = _PEER_CREDENTIALS.unpack(raw)
        except (OSError, TypeError, ValueError, struct.error) as exc:
            raise PeerCredentialsError("could not read SO_PEERCRED") from exc
        if pid <= 0 or uid < 0 or gid < 0:
            raise PeerCredentialsError("kernel returned invalid peer credentials")

        groups, verified = self._supplementary_groups(connection, pid, uid)
        return PeerCredentials(pid, uid, gid, groups, verified)

    def _supplementary_groups(
        self, connection: Any, pid: int, uid: int
    ) -> tuple[tuple[int, ...], bool]:
        # Linux documents this option as 59. Python versions without the
        # constant still need the kernel option.
        option = getattr(socket, "SO_PEERGROUPS", 59)
        try:
            raw = connection.getsockopt(socket.SOL_SOCKET, option, 1024)
            group_size = struct.calcsize("i")
            if isinstance(raw, bytes) and len(raw) % group_size == 0:
                groups = tuple(struct.unpack(f"{len(raw) // group_size}i", raw))
                if all(group >= 0 for group in groups):
                    return groups, True
        except (OSError, TypeError, ValueError, struct.error):
            pass
        # No kernel proof: do not infer identity from a pid path, which is
        # vulnerable to PID reuse and TOCTOU races.
        return (), False


def sys_is_linux() -> bool:
    """Small seam for tests and a clear supported-platform declaration."""

    return sys.platform == "linux" and hasattr(socket, "SO_PEERCRED")


@dataclass(frozen=True, slots=True)
class SocketLimits:
    """Resource limits applied before a command reaches the dispatcher."""

    max_request_bytes: int = MAX_REQUEST_BYTES
    max_response_bytes: int = MAX_RESPONSE_BYTES
    read_timeout: float = 5.0
    send_timeout: float = 5.0
    session_timeout: float = 300.0
    max_json_depth: int = 16
    max_request_id_length: int = 128
    max_command_length: int = 64
    max_args: int = 64
    max_arg_length: int = 4096
    max_args_bytes: int = 32 * 1024
    max_options_bytes: int = 16 * 1024
    max_container_exec_args: int = 32
    max_container_shell_args: int = 32
    max_mininet_cmd_args: int = 64
    max_interactive_sessions: int = 1
    max_connection_workers: int = 32

    @property
    def max_frame_bytes(self) -> int:
        """Name used by older integrations for the complete newline frame."""

        return self.max_request_bytes

    def __post_init__(self) -> None:
        numeric = (
            self.max_request_bytes,
            self.max_response_bytes,
            self.max_json_depth,
            self.max_request_id_length,
            self.max_command_length,
            self.max_args,
            self.max_arg_length,
            self.max_args_bytes,
            self.max_options_bytes,
            self.max_container_exec_args,
            self.max_container_shell_args,
            self.max_mininet_cmd_args,
            self.max_interactive_sessions,
            self.max_connection_workers,
        )
        if any(type(value) is not int or value <= 0 for value in numeric):
            raise ValueError("socket integer limits must be positive integers")
        timeouts = (self.read_timeout, self.send_timeout, self.session_timeout)
        if any(
            isinstance(value, bool)
            or not isinstance(value, Real)
            or not math.isfinite(value)
            or value <= 0
            for value in timeouts
        ):
            raise ValueError("socket timeouts must be positive")
        if self.max_request_bytes > MAX_REQUEST_BYTES:
            raise ValueError("socket frame limit cannot exceed 64 KiB")
        if self.max_response_bytes > MAX_RESPONSE_BYTES:
            raise ValueError("socket response limit cannot exceed 1 MiB")
        if self.max_response_bytes < MIN_RESPONSE_BYTES:
            raise ValueError("socket response limit is too small for a safe error envelope")


class AuditSink(Protocol):
    def info(self, message: str, *args: Any, **kwargs: Any) -> Any: ...


def _default_group_resolver(group_name: str) -> int:
    return grp.getgrnam(group_name).gr_gid


def _default_clock() -> float:
    return time.monotonic()


class NIEPSocketServer:
    """Serve authenticated, bounded v1 requests over an AF_UNIX socket."""

    def __init__(
        self,
        socket_path: str = "/run/niep.sock",
        dispatcher: Any = None,
        *,
        limits: SocketLimits | None = None,
        peer_provider: PeerCredentialsProvider | Callable[[Any], PeerCredentials] | None = None,
        group_name: str = SOCKET_GROUP,
        group_resolver: Callable[[str], int] | None = None,
        logger: AuditSink | Callable[[Mapping[str, Any]], Any] | None = None,
        clock: Callable[[], float] | None = None,
        socket_factory: Callable[..., Any] | None = None,
        secure_parent: bool = True,
        read_timeout: float | None = None,
        session_timeout: float | None = None,
        max_interactive_sessions: int | None = None,
        max_connection_workers: int | None = None,
        max_request_bytes: int | None = None,
        max_response_bytes: int | None = None,
    ) -> None:
        self.socket_path = os.fspath(socket_path)
        self.dispatcher = dispatcher or CommandDispatcher()
        self.socket: Any = None
        self.group_name = group_name
        self.group_resolver = group_resolver or _default_group_resolver
        self.peer_provider = peer_provider or LinuxPeerCredentialsProvider()
        if logger is None:
            self.logger = logging.getLogger("niep.socket")
            self.logger.setLevel(logging.INFO)
        else:
            self.logger = logger
        self.clock = clock or _default_clock
        self.socket_factory = socket_factory or socket.socket
        self.secure_parent = secure_parent
        selected_limits = limits or SocketLimits()
        overrides: dict[str, Any] = {}
        if read_timeout is not None:
            overrides["read_timeout"] = read_timeout
        if session_timeout is not None:
            overrides["session_timeout"] = session_timeout
        if max_interactive_sessions is not None:
            overrides["max_interactive_sessions"] = max_interactive_sessions
        if max_connection_workers is not None:
            overrides["max_connection_workers"] = max_connection_workers
        if max_request_bytes is not None:
            overrides["max_request_bytes"] = max_request_bytes
        if max_response_bytes is not None:
            overrides["max_response_bytes"] = max_response_bytes
        self.limits = replace(selected_limits, **overrides) if overrides else selected_limits
        self._interactive_slots = threading.BoundedSemaphore(self.limits.max_interactive_sessions)
        self._connection_slots = threading.BoundedSemaphore(self.limits.max_connection_workers)
        self._stop = threading.Event()
        self._connection_lock = threading.Lock()
        self._connections: set[Any] = set()
        self._interactive_streams: dict[int, Any] = {}
        self._bridge_workers: dict[int, tuple[threading.Thread, Any, Any]] = {}
        self._bridge_worker_slots = threading.BoundedSemaphore(self.limits.max_interactive_sessions)
        self._worker_threads: set[threading.Thread] = set()
        self._bound_identity: tuple[int, int] | None = None
        self._group_gid: int | None = None

    def serve_forever(self) -> None:
        self._prepare_socket()
        listening_socket = self.socket
        try:
            while not self._stop.is_set():
                try:
                    connection, _ = listening_socket.accept()
                except (OSError, socket.timeout):
                    if self._stop.is_set():
                        break
                    raise
                with self._connection_lock:
                    self._connections.add(connection)
                if not self._connection_slots.acquire(blocking=False):
                    self._close_quietly(connection)
                    with self._connection_lock:
                        self._connections.discard(connection)
                    continue
                worker = threading.Thread(
                    target=self._connection_worker,
                    args=(connection,),
                    name="niep-socket-client",
                    daemon=True,
                )
                with self._connection_lock:
                    self._worker_threads.add(worker)
                worker.start()
        finally:
            self.close()

    def _connection_worker(self, connection: Any) -> None:
        try:
            self._handle_connection(connection)
        finally:
            self._close_quietly(connection)
            self._connection_slots.release()
            with self._connection_lock:
                self._connections.discard(connection)
                self._worker_threads.discard(threading.current_thread())

    def close(self) -> None:
        self._stop.set()
        listening_socket = self.socket
        if listening_socket is not None:
            self._shutdown_and_close(listening_socket)
            self.socket = None
        with self._connection_lock:
            connections = tuple(self._connections)
            streams = tuple(self._interactive_streams.values())
            bridge_workers = tuple(self._bridge_workers.values())
        for connection in connections:
            self._shutdown_and_close(connection)
        for stream in streams:
            self._shutdown_stream(stream)
        for _thread, connection, stream in bridge_workers:
            self._shutdown_and_close(connection)
            self._shutdown_stream(stream)
        self._unlink_bound_socket()

    def _configured_group_gid(self) -> int:
        if self._group_gid is None:
            try:
                gid = self.group_resolver(self.group_name)
            except (KeyError, LookupError, OSError, TypeError, ValueError) as exc:
                raise PeerCredentialsError("configured socket group is unavailable") from exc
            if type(gid) is not int or gid < 0:
                raise PeerCredentialsError("configured socket group has an invalid gid")
            self._group_gid = gid
        return self._group_gid

    def _prepare_socket(self) -> None:
        path = Path(self.socket_path)
        if not path.is_absolute():
            raise RuntimeError("socket path must be absolute")
        if self.secure_parent:
            self._validate_parent(path.parent)
        group_gid = self._configured_group_gid()
        self._remove_stale_socket(path, group_gid)
        created = self.socket_factory(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket = created
        try:
            previous_umask = os.umask(0o117)
            try:
                created.bind(self.socket_path)
            finally:
                os.umask(previous_umask)
            metadata = os.stat(self.socket_path)
            self._bound_identity = (metadata.st_dev, metadata.st_ino)
            os.chown(self.socket_path, 0, group_gid)
            os.chmod(self.socket_path, SOCKET_MODE)
            final = os.stat(self.socket_path)
            if (
                not stat.S_ISSOCK(final.st_mode)
                or final.st_uid != 0
                or final.st_gid != group_gid
                or stat.S_IMODE(final.st_mode) != SOCKET_MODE
            ):
                raise RuntimeError("socket did not reach the required root:niep 0660 state")
            created.listen(5)
        except Exception:
            self._close_quietly(created)
            self.socket = None
            self._unlink_bound_socket()
            raise

    def _validate_parent(self, parent: Path) -> None:
        # Walk every component so a root-owned but symlinked parent cannot be
        # swapped underneath the daemon between validation and bind.
        current = Path(parent.anchor or os.sep)
        for component in parent.parts[1:]:
            current /= component
            try:
                metadata = os.lstat(current)
            except OSError as exc:
                raise RuntimeError("socket parent does not exist") from exc
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
                raise RuntimeError("socket parent contains a symlink or non-directory")
            if metadata.st_uid != 0:
                raise RuntimeError("socket parent is not owned by root")
            if metadata.st_mode & 0o022:
                raise RuntimeError("socket parent is group/world writable")

    def _remove_stale_socket(self, path: Path, group_gid: int) -> None:
        try:
            metadata = os.lstat(path)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise RuntimeError("could not inspect existing socket path") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISSOCK(metadata.st_mode):
            raise RuntimeError("refusing to unlink a non-socket socket path")
        if metadata.st_uid != 0 or metadata.st_gid != group_gid:
            raise RuntimeError("existing socket has unexpected ownership")
        if stat.S_IMODE(metadata.st_mode) != SOCKET_MODE:
            raise RuntimeError("existing socket has unexpected permissions")
        original_identity = (metadata.st_dev, metadata.st_ino)
        probe = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            probe.settimeout(0.2)
            probe.connect(os.fspath(path))
        except (ConnectionRefusedError, FileNotFoundError, NotADirectoryError):
            pass
        except OSError as exc:
            if exc.errno not in {errno.ECONNREFUSED, errno.ENOENT, errno.ENOTCONN}:
                raise RuntimeError("existing socket could not be validated") from exc
        else:
            raise RuntimeError("existing NIEP socket is already active")
        finally:
            self._close_quietly(probe)
        current = os.lstat(path)
        if (current.st_dev, current.st_ino) != original_identity:
            raise RuntimeError("socket path changed while validating stale state")
        os.unlink(path)

    def _unlink_bound_socket(self) -> None:
        identity = self._bound_identity
        self._bound_identity = None
        if identity is None:
            return
        try:
            metadata = os.lstat(self.socket_path)
        except FileNotFoundError:
            return
        except OSError:
            return
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISSOCK(metadata.st_mode):
            return
        if identity is not None and (metadata.st_dev, metadata.st_ino) != identity:
            return
        try:
            os.unlink(self.socket_path)
        except OSError:
            pass

    def _peer_credentials(self, connection: Any) -> PeerCredentials:
        provider = self.peer_provider
        try:
            if callable(provider) and not hasattr(provider, "get_peer_credentials"):
                credentials = provider(connection)
            else:
                credentials = provider.get_peer_credentials(connection)  # type: ignore[union-attr]
        except PeerCredentialsError:
            raise
        except Exception as exc:
            raise PeerCredentialsError("could not authenticate socket peer") from exc
        if isinstance(credentials, PeerCredentials):
            return credentials
        if isinstance(credentials, Mapping):
            try:
                return PeerCredentials(
                    pid=credentials["pid"],
                    uid=credentials["uid"],
                    gid=credentials["gid"],
                    supplementary_groups=tuple(credentials.get("supplementary_groups", ())),
                    supplementary_verified=credentials.get("supplementary_verified", True),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise PeerCredentialsError("peer provider returned invalid credentials") from exc
        raise PeerCredentialsError("peer provider returned invalid credentials")

    def _authorize(self, connection: Any) -> PeerCredentials:
        credentials = self._peer_credentials(connection)
        self._authorize_credentials(credentials)
        return credentials

    def _authorize_credentials(self, credentials: PeerCredentials) -> None:
        if (
            type(credentials.pid) is not int
            or credentials.pid <= 0
            or type(credentials.uid) is not int
            or credentials.uid < 0
            or type(credentials.gid) is not int
            or credentials.gid < 0
        ):
            raise PeerCredentialsError("peer provider returned invalid credentials")
        if any(type(group) is not int or group < 0 for group in credentials.supplementary_groups):
            raise PeerCredentialsError("peer provider returned invalid supplementary groups")
        if type(credentials.supplementary_verified) is not bool:
            raise PeerCredentialsError("peer provider returned invalid group verification")
        if credentials.uid == 0:
            return
        group_gid = self._configured_group_gid()
        if credentials.gid == group_gid:
            return
        if credentials.supplementary_verified and group_gid in credentials.supplementary_groups:
            return
        raise UnauthorizedPeer("socket peer is not authorized")

    def _handle_connection(self, connection: Any) -> None:
        started = self.clock()
        credentials: PeerCredentials | None = None
        request: CommandRequest | None = None
        try:
            try:
                credentials = self._peer_credentials(connection)
                self._authorize_credentials(credentials)
            except UnauthorizedPeer:
                self._audit(None, credentials, "unauthorized", False, started)
                self._send_response(
                    connection,
                    CommandResponse.failure("unauthorized", "unauthorized", "unauthorized peer"),
                )
                return
            except PeerCredentialsError:
                self._audit(None, credentials, "authentication_error", False, started)
                self._send_response(
                    connection,
                    CommandResponse.failure(
                        "unauthorized", "unauthorized", "peer authentication failed"
                    ),
                )
                return

            read_deadline = self.clock() + self.limits.read_timeout
            request = self._read_request(connection, deadline=read_deadline)
            if self._is_interactive_shell(request):
                self._handle_interactive_shell(
                    connection, request, credentials=credentials, started=started
                )
                return
            response = self.handle_request(request)
            self._send_response(connection, response)
            self._audit(
                request,
                credentials,
                response.get("code", "unknown"),
                bool(response.get("ok")),
                started,
            )
        except (
            SocketProtocolError,
            CommandProtocolError,
            ValueError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ) as exc:
            code = getattr(exc, "code", "invalid_request")
            request_id = (
                request.request_id
                if request is not None
                else getattr(exc, "request_id", self._request_id_from_connection_error(exc))
            )
            response = CommandResponse.failure(request_id, code, self._safe_protocol_message(code))
            self._send_response(connection, response)
            self._audit(request, credentials, code, False, started)
        except (socket.timeout, TimeoutError):
            response = CommandResponse.failure(
                request.request_id if request else "timeout", "timeout", "request timed out"
            )
            self._send_response(connection, response)
            self._audit(request, credentials, "timeout", False, started)
        except Exception:
            # Do not turn runtime exception text, command contents or a
            # traceback into a privileged API response or an audit record.
            response = CommandResponse.failure(
                request.request_id if request else "internal",
                "internal_error",
                "internal server error",
            )
            self._send_response(connection, response)
            self._audit(request, credentials, "internal_error", False, started)

    def _request_id_from_connection_error(self, _exc: Exception) -> str:
        # The request is intentionally not retained on parsing failure.  A
        # stable non-secret correlation id still lets clients identify the
        # rejection, while a malformed request cannot choose arbitrary text.
        return "invalid"

    def _read_request(self, connection: Any, *, deadline: float | None = None) -> CommandRequest:
        deadline = self.clock() + self.limits.read_timeout if deadline is None else deadline
        limit = self.limits.max_request_bytes
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = self._recv_with_deadline(connection, min(4096, limit + 1 - size), deadline)
            if not chunk:
                if not chunks:
                    raise SocketProtocolError("empty command request", code="empty_request")
                raise SocketProtocolError("request ended before newline", code="truncated_request")
            if not isinstance(chunk, bytes):
                raise SocketProtocolError("socket returned non-bytes data", code="invalid_request")
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                raise SocketProtocolError(
                    "request exceeds the 64 KiB limit", code="request_too_large"
                )
            if b"\n" in chunk:
                payload, separator, trailing = b"".join(chunks).partition(b"\n")
                if trailing:
                    raise SocketProtocolError("bytes after request frame", code="trailing_data")
                frame_size = len(payload) + len(separator)
                if frame_size > limit:
                    raise SocketProtocolError(
                        "request exceeds the 64 KiB limit", code="request_too_large"
                    )
                if not payload.strip():
                    raise SocketProtocolError("empty command request", code="empty_request")
                try:
                    text = payload.decode("utf-8")
                    parsed = json.loads(
                        text,
                        parse_constant=self._reject_json_constant,
                        object_pairs_hook=self._reject_duplicate_keys,
                    )
                except UnicodeDecodeError as exc:
                    raise SocketProtocolError(
                        "request is not valid UTF-8", code="invalid_json"
                    ) from exc
                except RecursionError as exc:
                    raise SocketProtocolError(
                        "JSON nesting is too deep", code="json_too_deep"
                    ) from exc
                except (json.JSONDecodeError, ValueError) as exc:
                    raise SocketProtocolError(
                        "request is not valid JSON", code="invalid_json"
                    ) from exc
                self._validate_json_depth(parsed)
                if not isinstance(parsed, Mapping):
                    raise SocketProtocolError(
                        "command request must be a JSON object", code="invalid_request"
                    )
                self._validate_raw_request(parsed)
                try:
                    request = CommandRequest.from_dict(parsed)
                except CommandProtocolError as exc:
                    raise SocketProtocolError(
                        self._safe_protocol_message(exc.code),
                        code=exc.code,
                        request_id=parsed.get("request_id", "invalid"),
                    ) from exc
                try:
                    self._validate_request_limits(request)
                except SocketProtocolError as exc:
                    raise SocketProtocolError(
                        str(exc), code=exc.code, request_id=request.request_id
                    ) from exc
                if not self._is_interactive_shell(request):
                    self._require_request_eof(connection, request, deadline)
                return request

    def _require_request_eof(
        self, connection: Any, request: CommandRequest, deadline: float
    ) -> None:
        """Require a half-closed request side before dispatching one-shot calls."""

        while True:
            chunk = self._recv_with_deadline(connection, 4096, deadline)
            if not chunk:
                return
            raise SocketProtocolError(
                "bytes after request frame", code="trailing_data", request_id=request.request_id
            )

    def _recv_with_deadline(self, connection: Any, size: int, deadline: float) -> bytes:
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise SocketProtocolError("request timed out", code="timeout")
        self._set_timeout(connection, remaining)
        try:
            return connection.recv(size)
        except (socket.timeout, TimeoutError) as exc:
            raise SocketProtocolError("request timed out", code="timeout") from exc

    @staticmethod
    def _validate_raw_request(payload: Mapping[str, Any]) -> None:
        command = payload.get("command")
        if isinstance(command, str) and any(
            ord(char) < 0x20 or ord(char) == 0x7F for char in command
        ):
            request_id = payload.get("request_id", "invalid")
            raise SocketProtocolError(
                "command contains control characters",
                code="invalid_request",
                request_id=request_id if isinstance(request_id, str) else "invalid",
            )

    @staticmethod
    def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON field")
            result[key] = value
        return result

    @staticmethod
    def _reject_json_constant(value: str) -> None:
        raise ValueError("non-finite JSON value: " + value)

    def _validate_json_depth(self, value: Any, depth: int = 0) -> None:
        if depth > self.limits.max_json_depth:
            raise SocketProtocolError("JSON nesting is too deep", code="json_too_deep")
        if isinstance(value, Mapping):
            for key, item in value.items():
                if not isinstance(key, str):
                    raise SocketProtocolError(
                        "JSON object keys must be strings", code="invalid_request"
                    )
                self._validate_json_depth(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                self._validate_json_depth(item, depth + 1)

    def _validate_request_limits(self, request: CommandRequest) -> None:
        if len(request.request_id) > self.limits.max_request_id_length:
            raise SocketProtocolError("request_id is too long", code="request_too_large")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in request.request_id):
            raise SocketProtocolError(
                "request_id contains control characters", code="invalid_request"
            )
        if len(request.command) > self.limits.max_command_length:
            raise SocketProtocolError("command name is too long", code="request_too_large")
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in request.command):
            raise SocketProtocolError("command contains control characters", code="invalid_request")
        if len(request.args) > self.limits.max_args:
            raise SocketProtocolError("too many command arguments", code="request_too_large")
        if any(len(argument) > self.limits.max_arg_length for argument in request.args):
            raise SocketProtocolError("command argument is too long", code="request_too_large")
        try:
            args_bytes = sum(len(argument.encode("utf-8")) for argument in request.args)
        except UnicodeEncodeError as exc:
            raise SocketProtocolError(
                "command arguments are not valid UTF-8", code="invalid_request"
            ) from exc
        if args_bytes > self.limits.max_args_bytes:
            raise SocketProtocolError("command arguments are too large", code="request_too_large")
        try:
            options_size = len(
                json.dumps(
                    request.to_dict()["options"], separators=(",", ":"), ensure_ascii=False
                ).encode("utf-8")
            )
        except (TypeError, ValueError, UnicodeError) as exc:
            raise SocketProtocolError("invalid command options", code="invalid_request") from exc
        if options_size > self.limits.max_options_bytes:
            raise SocketProtocolError("command options are too large", code="request_too_large")

        args = request.args
        if request.command == "container" and args:
            operation = args[0]
            if operation == "exec" and len(args) - 2 > self.limits.max_container_exec_args:
                raise SocketProtocolError(
                    "container exec command is too large", code="request_too_large"
                )
            if operation == "shell" and len(args) - 2 > self.limits.max_container_shell_args:
                raise SocketProtocolError(
                    "container shell command is too large", code="request_too_large"
                )
        if request.command == "mininet" and args and args[0] == "cmd":
            if len(args) - 2 > self.limits.max_mininet_cmd_args:
                raise SocketProtocolError("mininet command is too large", code="request_too_large")

    def _is_interactive_shell(self, request: CommandRequest | Mapping[str, Any]) -> bool:
        if isinstance(request, CommandRequest):
            args = request.args
            return request.command == "container" and len(args) >= 2 and args[0] == "shell"
        args = request.get("args", [])
        if not isinstance(args, (list, tuple)) or any(not isinstance(arg, str) for arg in args):
            return False
        return request.get("command") == "container" and len(args) >= 2 and args[0] == "shell"

    def _handle_interactive_shell(
        self,
        connection: Any,
        request: CommandRequest | Mapping[str, Any],
        *,
        credentials: PeerCredentials | None = None,
        started: float | None = None,
    ) -> None:
        request = (
            request if isinstance(request, CommandRequest) else CommandRequest.from_dict(request)
        )
        started = self.clock() if started is None else started
        if not self._interactive_slots.acquire(blocking=False):
            response = CommandResponse.failure(
                request.request_id, "interactive_limit", "too many interactive sessions"
            )
            self._send_response(connection, response)
            self._audit(request, credentials, response.code, False, started)
            return
        stream: Any = None
        response_sent = False
        bridge_slot_acquired = False
        try:
            result = self.dispatcher.open_stream("container", request.args)
            stream = result.data
            if stream is not None and not self._register_interactive_stream(stream):
                self._audit(request, credentials, "server_closing", False, started)
                return
            response = CommandResponse.from_result(request, result)
            if result.ok:
                if not self._bridge_worker_slots.acquire(blocking=False):
                    response = CommandResponse.failure(
                        request.request_id,
                        "stream_worker_limit",
                        "interactive stream unavailable",
                    )
                    self._send_response(connection, response)
                    self._audit(request, credentials, response.code, False, started)
                    return
                bridge_slot_acquired = True
            response_sent = self._send_response(connection, response)
            if not result.ok:
                self._audit(request, credentials, response.code, False, started)
                return
            if not response_sent:
                # The client disappeared before the stream was handed over;
                # never leak the runtime stream while attempting to bridge.
                return
            bridge_ok, bridge_result = self._bridge_with_timeout(
                connection, stream, slot_acquired=True
            )
            bridge_slot_acquired = False
            self._audit(request, credentials, bridge_result, bridge_ok, started)
        except Exception:
            if not response_sent:
                self._send_response(
                    connection,
                    CommandResponse.failure(
                        request.request_id, "internal_error", "internal server error"
                    ),
                )
            self._audit(request, credentials, "internal_error", False, started)
        finally:
            if bridge_slot_acquired:
                self._bridge_worker_slots.release()
            self._shutdown_stream(stream)
            self._unregister_interactive_stream(stream)
            self._interactive_slots.release()

    def _bridge_with_timeout(
        self, connection: Any, stream: Any, *, slot_acquired: bool = False
    ) -> tuple[bool, str]:
        # Always run the bridge in a bounded daemon worker.  A select deadline
        # cannot protect this caller from a blocked recv/sendall, so the
        # watchdog must be able to close both endpoints independently.
        token_acquired = slot_acquired
        worker_started = False
        worker: threading.Thread | None = None
        tracked = False
        lease_released = False
        try:
            if not token_acquired:
                if not self._bridge_worker_slots.acquire(blocking=False):
                    return False, "stream_worker_limit"
                token_acquired = True

            def release_once() -> None:
                nonlocal lease_released
                with self._connection_lock:
                    if lease_released:
                        return
                    lease_released = True
                self._bridge_worker_slots.release()

            try:
                parameters = inspect.signature(bridge_sockets).parameters
            except (TypeError, ValueError):
                parameters = {}

            finished = threading.Event()
            outcome: list[tuple[bool, str]] = []

            def bridge() -> None:
                try:
                    if "timeout" in parameters:
                        completed = bridge_sockets(
                            connection, stream, timeout=self.limits.session_timeout
                        )
                    else:
                        completed = bridge_sockets(connection, stream)
                    outcome.append(
                        (
                            completed is not False,
                            "stream_closed" if completed is not False else "session_timeout",
                        )
                    )
                except (socket.timeout, TimeoutError):
                    outcome.append((False, "session_timeout"))
                except BaseException as exc:  # ensure cleanup happens in caller
                    del exc
                    outcome.append((False, "stream_error"))
                finally:
                    try:
                        with self._connection_lock:
                            current = self._bridge_workers.get(id(worker))
                            if current is not None and current[0] is worker:
                                self._bridge_workers.pop(id(worker), None)
                    finally:
                        release_once()
                        finished.set()

            worker = threading.Thread(target=bridge, name="niep-socket-stream", daemon=True)
            with self._connection_lock:
                if self._stop.is_set():
                    cancel = True
                else:
                    cancel = False
                    self._bridge_workers[id(worker)] = (worker, connection, stream)
                    tracked = True
            if cancel:
                self._shutdown_and_close(connection)
                self._shutdown_stream(stream)
                return False, "server_closing"

            try:
                worker.start()
            except BaseException:
                try:
                    worker_started = worker.ident is not None or worker.is_alive()
                except BaseException:
                    worker_started = False
                if worker_started:
                    self._shutdown_and_close(connection)
                    self._shutdown_stream(stream)
                    return False, "stream_error"
                raise
            worker_started = True
            if not finished.wait(self.limits.session_timeout):
                self._shutdown_and_close(connection)
                self._shutdown_stream(stream)
                return False, "session_timeout"
            return outcome[0] if outcome else (False, "stream_error")
        except BaseException:
            if worker_started:
                self._shutdown_and_close(connection)
                self._shutdown_stream(stream)
            return False, "stream_error"
        finally:
            if not worker_started:
                if tracked and worker is not None:
                    with self._connection_lock:
                        current = self._bridge_workers.get(id(worker))
                        if current is not None and current[0] is worker:
                            self._bridge_workers.pop(id(worker), None)
                if token_acquired:
                    release_once()

    def _register_interactive_stream(self, stream: Any) -> bool:
        """Track an opened stream so global shutdown can close it safely."""

        should_close = False
        with self._connection_lock:
            if self._stop.is_set():
                should_close = True
            else:
                self._interactive_streams[id(stream)] = stream
        if should_close:
            self._shutdown_stream(stream)
            return False
        return True

    def _unregister_interactive_stream(self, stream: Any) -> None:
        if stream is None:
            return
        with self._connection_lock:
            if self._interactive_streams.get(id(stream)) is stream:
                self._interactive_streams.pop(id(stream), None)

    @staticmethod
    def _stream_socket(stream: Any) -> Any:
        return getattr(stream, "_sock", stream)

    @classmethod
    def _shutdown_stream(cls, stream: Any) -> None:
        if stream is None:
            return
        underlying = cls._stream_socket(stream)
        cls._shutdown_and_close(underlying)
        if underlying is not stream:
            cls._shutdown_and_close(stream)

    def handle_request(self, request: CommandRequest | Mapping[str, Any]) -> dict[str, Any]:
        try:
            if hasattr(self.dispatcher, "dispatch_request"):
                response = self.dispatcher.dispatch_request(request)
                return self._public_socket_payload(response.to_dict())
            normalized = (
                request
                if isinstance(request, CommandRequest)
                else CommandRequest.from_dict(request)
            )
            result = _public_result(self.dispatcher.dispatch(normalized.command, normalized.args))
            return self._public_socket_payload(
                CommandResponse.from_result(normalized, result).to_dict()
            )
        except CommandProtocolError as exc:
            request_id = request.request_id if isinstance(request, CommandRequest) else "invalid"
            return self._public_socket_payload(
                CommandResponse.failure(
                    request_id, exc.code, self._safe_protocol_message(exc.code)
                ).to_dict()
            )
        except Exception:
            request_id = request.request_id if isinstance(request, CommandRequest) else "internal"
            return self._public_socket_payload(
                CommandResponse.failure(
                    request_id, "internal_error", "internal server error"
                ).to_dict()
            )

    @staticmethod
    def _public_socket_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        """Return only the documented, JSON-safe response envelope."""

        allowed = {
            "protocol",
            "version",
            "request_id",
            "ok",
            "code",
            "message",
            "data",
            "status",
            "exit_code",
            "stream",
        }
        public = {key: value for key, value in payload.items() if key in allowed}
        public["request_id"] = NIEPSocketServer._safe_request_id(public.get("request_id"))
        public.pop("detail", None)
        code = public.get("code")
        if not public.get("ok") and code != "container_exec":
            public.pop("data", None)
        return public

    @staticmethod
    def _safe_request_id(value: Any) -> str:
        if not isinstance(value, str) or not value:
            return "invalid"
        if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
            return "invalid"
        if len(value) > 128:
            return "invalid"
        return value

    def _send_response(
        self, connection: Any, response: CommandResponse | Mapping[str, Any]
    ) -> bool:
        payload = response.to_dict() if isinstance(response, CommandResponse) else dict(response)
        payload = self._public_socket_payload(payload)
        try:
            encoded = (json.dumps(payload, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            payload = {
                "protocol": "niep.command",
                "version": 1,
                "request_id": "internal",
                "ok": False,
                "code": "internal_error",
                "message": "internal server error",
                "exit_code": 1,
            }
            encoded = (json.dumps(payload, allow_nan=False) + "\n").encode("utf-8")
        if len(encoded) > self.limits.max_response_bytes:
            payload = {
                "protocol": "niep.command",
                "version": 1,
                "request_id": "response",
                "ok": False,
                "code": "response_too_large",
                "message": "response exceeds configured limits",
                "exit_code": 1,
            }
            encoded = (json.dumps(payload, allow_nan=False) + "\n").encode("utf-8")
        self._set_timeout(connection, self.limits.send_timeout)
        try:
            connection.sendall(encoded)
        except (BrokenPipeError, ConnectionError, OSError):
            return False
        return True

    @staticmethod
    def _set_timeout(connection: Any, timeout: float) -> None:
        setter = getattr(connection, "settimeout", None)
        if setter is not None:
            setter(timeout)

    @staticmethod
    def _close_quietly(resource: Any) -> None:
        if resource is None:
            return
        try:
            resource.close()
        except Exception:
            pass

    @staticmethod
    def _shutdown_and_close(resource: Any) -> None:
        if resource is None:
            return
        shutdown = getattr(resource, "shutdown", None)
        if shutdown is not None:
            try:
                shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
        NIEPSocketServer._close_quietly(resource)

    def _audit(
        self,
        request: CommandRequest | None,
        credentials: PeerCredentials | None,
        result: str,
        ok: bool,
        started: float,
    ) -> None:
        elapsed = max(0.0, self.clock() - started)
        args = request.args if request is not None else ()
        command = self._audit_text(request.command) if request is not None else "<authentication>"
        resource = self._safe_resource(command, args)
        record = {
            "event": "socket_request",
            "request_id": (
                self._safe_request_id(request.request_id) if request is not None else "invalid"
            ),
            "peer_pid": credentials.pid if credentials is not None else None,
            "peer_uid": credentials.uid if credentials is not None else None,
            "peer_gid": credentials.gid if credentials is not None else None,
            "command": command,
            "resource": resource,
            "duration_ms": round(elapsed * 1000, 3),
            "result": self._audit_text(str(result), 64),
            "ok": ok,
        }
        logger = self.logger
        try:
            message = json.dumps(record, sort_keys=True, separators=(",", ":"))
            if callable(logger) and not hasattr(logger, "info"):
                logger(record)
            else:
                logger.info(message, extra={"niep_audit": record})  # type: ignore[union-attr]
        except Exception:
            # Audit failures must not take down the privileged daemon, and no
            # fallback may accidentally log the request arguments.
            pass

    @staticmethod
    def _safe_resource(command: str, args: tuple[str, ...]) -> str | None:
        if command in {"container", "vm", "vnf", "sfc"} and len(args) >= 2:
            return NIEPSocketServer._audit_text(args[1])
        if command == "mininet" and len(args) >= 2 and args[0] == "cmd":
            return NIEPSocketServer._audit_text(args[1])
        if command == "define":
            return "<topology>"
        return None

    @staticmethod
    def _audit_text(value: str, limit: int = 96) -> str:
        safe = "".join(char if 0x20 <= ord(char) < 0x7F else "?" for char in value)
        return safe[:limit]

    @staticmethod
    def _safe_protocol_message(code: str) -> str:
        messages = {
            "empty_request": "empty command request",
            "truncated_request": "request ended before newline",
            "request_too_large": "request exceeds configured limits",
            "trailing_data": "bytes after request frame",
            "invalid_json": "request is not valid JSON",
            "json_too_deep": "JSON nesting is too deep",
            "timeout": "request timed out",
            "unsupported_version": "unsupported command protocol version",
            "invalid_request": "invalid command request",
        }
        return messages.get(code, "invalid command request")
