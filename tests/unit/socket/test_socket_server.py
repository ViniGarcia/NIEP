from __future__ import annotations

import json
import logging
import os
import socket
import struct
import threading
import time
from pathlib import Path

import pytest

from niep.application.commands import CommandRequest
from niep.domain.result import ResultCode, ServiceResult
from niep.interfaces.socket_server import (
    LinuxPeerCredentialsProvider,
    NIEPSocketServer,
    PeerCredentials,
    SocketLimits,
)
from niep.runtime.terminal_session import bridge_sockets, bridge_terminal


class Connection:
    def __init__(self, *chunks: bytes, send_error: Exception | None = None):
        self.chunks = list(chunks)
        self.sent: list[bytes] = []
        self.timeouts: list[float] = []
        self.send_error = send_error
        self.closed = False

    def recv(self, _size: int) -> bytes:
        return self.chunks.pop(0) if self.chunks else b""

    def sendall(self, payload: bytes) -> None:
        if self.send_error:
            raise self.send_error
        self.sent.append(payload)

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)

    def close(self) -> None:
        self.closed = True


class PeerProvider:
    def __init__(self, credentials: PeerCredentials):
        self.credentials = credentials

    def get_peer_credentials(self, _connection):
        return self.credentials


class Dispatcher:
    def __init__(self):
        self.calls = 0

    def dispatch_request(self, request):
        self.calls += 1
        request = (
            request if isinstance(request, CommandRequest) else CommandRequest.from_dict(request)
        )
        return type(
            "Response",
            (),
            {
                "to_dict": lambda _self: {
                    "protocol": "niep.command",
                    "version": 1,
                    "request_id": request.request_id,
                    "ok": True,
                    "code": "status",
                    "message": "",
                    "data": {"safe": True},
                    "detail": "internal detail must not cross the socket",
                    "cause": "secret cause",
                    "traceback": "secret traceback",
                    "unknown": "must be dropped",
                    "exit_code": 0,
                }
            },
        )()


def server(dispatcher=None, **kwargs):
    kwargs.setdefault("peer_provider", PeerProvider(PeerCredentials(123, 1000, 1000, (), True)))
    kwargs.setdefault("logger", lambda _record: None)
    return NIEPSocketServer(
        dispatcher=dispatcher or Dispatcher(),
        group_resolver=lambda _name: 1000,
        **kwargs,
    )


def response(connection: Connection) -> dict:
    return json.loads(connection.sent[-1].decode())


def test_unauthorized_peer_is_rejected_before_dispatcher():
    dispatcher = Dispatcher()
    instance = NIEPSocketServer(
        dispatcher=dispatcher,
        peer_provider=PeerProvider(PeerCredentials(123, 1000, 2000, (), False)),
        group_resolver=lambda _name: 1000,
        logger=lambda _record: None,
    )
    connection = Connection(b'{"command":"status"}\n')

    instance._handle_connection(connection)

    assert dispatcher.calls == 0
    assert response(connection)["code"] == "unauthorized"


@pytest.mark.parametrize(
    ("payload", "code"),
    [
        (b"", "empty_request"),
        (b'{"command":"status"}', "truncated_request"),
        (b'{"command":"status"}\nextra', "trailing_data"),
        (b'{"command":"status","command":"vm"}\n', "invalid_json"),
        (b'{"command":"status","options":{"value":NaN}}\n', "invalid_json"),
        (b'{"command":"status","unknown":true}\n', "invalid_request"),
        (b'{"command":"status","version":2}\n', "unsupported_version"),
    ],
)
def test_invalid_frames_are_rejected_before_dispatch(payload, code):
    dispatcher = Dispatcher()
    instance = server(dispatcher)
    connection = Connection(payload)

    instance._handle_connection(connection)

    assert dispatcher.calls == 0
    assert response(connection)["code"] == code


def test_second_frame_in_a_later_recv_is_rejected_before_dispatch():
    dispatcher = Dispatcher()
    instance = server(dispatcher)
    connection = Connection(b'{"command":"status"}\n', b'{"command":"status"}\n')

    instance._handle_connection(connection)

    assert dispatcher.calls == 0
    assert response(connection)["code"] == "trailing_data"


def test_raw_command_controls_are_rejected_before_normalization():
    dispatcher = Dispatcher()
    instance = server(dispatcher)
    connection = Connection(b'{"command":"\\tstatus","request_id":"request-1"}\n')

    instance._handle_connection(connection)

    assert dispatcher.calls == 0
    assert response(connection)["code"] == "invalid_request"


def test_long_or_control_request_ids_are_not_echoed_in_responses():
    for request_id in ("x" * 60_000, "bad\nrequest"):
        connection = Connection(
            json.dumps({"command": "status", "request_id": request_id}).encode() + b"\n"
        )
        server()._handle_connection(connection)
        encoded = connection.sent[-1]
        assert len(encoded) < 192
        assert b"x" * 256 not in encoded
        assert b"bad\\nrequest" not in encoded


def test_frame_and_json_depth_limits_are_enforced():
    dispatcher = Dispatcher()
    instance = server(dispatcher, limits=SocketLimits(max_request_bytes=20, max_json_depth=2))
    oversized = Connection(b'{"command":"status","args":[]}\n')
    instance._handle_connection(oversized)
    assert response(oversized)["code"] == "request_too_large"

    deep = json.dumps({"command": "status", "options": {"a": {"b": 1}}}).encode() + b"\n"
    connection = Connection(deep)
    server(dispatcher, limits=SocketLimits(max_json_depth=2))._handle_connection(connection)
    assert response(connection)["code"] == "json_too_deep"


def test_request_is_normalized_and_audit_does_not_contain_args():
    records = []
    instance = server(logger=records.append)
    connection = Connection(b'{"command":"container","args":["exec","c1","secret-token"]}\n')

    instance._handle_connection(connection)

    assert response(connection)["request_id"]
    assert records
    record = records[0]
    assert record["command"] == "container"
    assert record["resource"] == "c1"
    assert "secret-token" not in repr(record)
    assert connection.timeouts[0] <= 5.0
    assert connection.timeouts[-1] == 5.0


def test_public_response_is_a_whitelist_without_internal_fields():
    connection = Connection(b'{"command":"status"}\n')
    server()._handle_connection(connection)
    public = response(connection)
    assert "detail" not in public
    assert "cause" not in public
    assert "traceback" not in public
    assert "unknown" not in public


def test_oversized_response_is_replaced_by_a_bounded_error():
    instance = server(limits=SocketLimits(max_response_bytes=192))
    connection = Connection()
    assert instance._send_response(
        connection,
        {
            "protocol": "niep.command",
            "version": 1,
            "request_id": "request-1",
            "ok": True,
            "code": "status",
            "message": "",
            "data": {"output": "x" * 10_000},
            "exit_code": 0,
        },
    )
    assert len(connection.sent[-1]) <= 192
    assert response(connection)["code"] == "response_too_large"


def test_default_response_limit_supports_a_512_container_disk_snapshot():
    instance = server()
    connection = Connection()
    resources = [dict(kind='container', id=f'c{i}', disk_bytes=4096,
                      source='host_allocated_blocks', image_id='sha256:' + 'a' * 64,
                      image_bytes=12395808, image_source='docker_image_size',
                      error=None, image_error=None) for i in range(512)]
    assert instance._send_response(connection, {
        'protocol': 'niep.command', 'version': 1, 'request_id': 'large-snapshot',
        'ok': True, 'code': 'disk_usage', 'data': {'resources': resources}, 'exit_code': 0})
    assert 64 * 1024 < len(connection.sent[-1]) <= SocketLimits().max_response_bytes
    assert response(connection)['data']['resources'] == resources


def test_total_read_deadline_rejects_drip_feed():
    class SlowConnection(Connection):
        def recv(self, size):
            import time

            time.sleep(0.04)
            return super().recv(size)

    dispatcher = Dispatcher()
    instance = server(dispatcher, read_timeout=0.05)
    connection = SlowConnection(b'{"command":"status"}', b"\n", b"")

    instance._handle_connection(connection)

    assert dispatcher.calls == 0
    assert response(connection)["code"] == "timeout"


def test_default_audit_is_visible_as_json_without_secrets(caplog):
    caplog.set_level(logging.INFO, logger="niep.socket")
    instance = NIEPSocketServer(
        dispatcher=Dispatcher(),
        peer_provider=PeerProvider(PeerCredentials(123, 1000, 1000)),
        group_resolver=lambda _name: 1000,
    )
    connection = Connection(b'{"command":"container","args":["exec","c1","secret-password"]}\n')

    instance._handle_connection(connection)

    messages = [record.getMessage() for record in caplog.records if record.name == "niep.socket"]
    assert messages
    assert '"peer_uid":1000' in messages[-1]
    assert '"command":"container"' in messages[-1]
    assert "secret-password" not in messages[-1]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"read_timeout": float("nan")},
        {"send_timeout": float("inf")},
        {"session_timeout": True},
        {"max_response_bytes": 1024 * 1024 + 1},
        {"max_response_bytes": 191},
    ],
)
def test_limits_reject_non_finite_boolean_or_oversized_values(kwargs):
    with pytest.raises(ValueError):
        SocketLimits(**kwargs)


def test_close_shutdown_wakes_blocked_accept():
    import threading

    class Listener:
        def __init__(self):
            self.wake = threading.Event()
            self.entered = threading.Event()
            self.closed = False

        def accept(self):
            self.entered.set()
            self.wake.wait()
            raise OSError("listener shut down")

        def shutdown(self, _how):
            self.wake.set()

        def close(self):
            self.closed = True
            self.wake.set()

    listener = Listener()
    instance = server()
    instance._prepare_socket = lambda: setattr(instance, "socket", listener)
    thread = threading.Thread(target=instance.serve_forever)
    thread.start()
    assert listener.entered.wait(1)
    instance.close()
    thread.join(timeout=1)
    assert not thread.is_alive()
    assert listener.closed is True


def test_primary_and_verified_supplementary_group_are_authorized():
    assert server(peer_provider=PeerProvider(PeerCredentials(123, 1000, 1000)))._authorize(
        Connection()
    )
    assert server(
        peer_provider=PeerProvider(PeerCredentials(123, 1000, 2000, (1000,), True))
    )._authorize(Connection())
    with pytest.raises(PermissionError):
        server(
            peer_provider=PeerProvider(PeerCredentials(123, 1000, 2000, (1000,), False))
        )._authorize(Connection())


def test_linux_provider_reads_kernel_credentials_and_fails_closed_without_groups():
    class KernelConnection:
        def getsockopt(self, level, option, length):
            assert level == socket.SOL_SOCKET
            if option == socket.SO_PEERCRED:
                return struct.pack("3i", 123, 1000, 2000)
            raise OSError("SO_PEERGROUPS unavailable")

    credentials = LinuxPeerCredentialsProvider().get_peer_credentials(KernelConnection())
    assert credentials.pid == 123
    assert credentials.uid == 1000
    assert credentials.gid == 2000
    assert credentials.supplementary_verified is False


def test_linux_provider_reads_real_socketpair_peer_groups_with_1024_buffer():
    left, right = socket.socketpair()
    try:
        credentials = LinuxPeerCredentialsProvider().get_peer_credentials(left)
        assert credentials.pid > 0
        assert credentials.uid == os.getuid()
        assert credentials.supplementary_verified is True
    finally:
        left.close()
        right.close()


def test_shell_closes_stream_if_header_send_fails(monkeypatch):
    class Stream:
        closed = False

        def close(self):
            self.closed = True

    stream = Stream()
    dispatcher = Dispatcher()
    dispatcher.open_stream = lambda *_: ServiceResult(True, ResultCode.CONTAINER_SHELL, data=stream)
    bridged = []
    monkeypatch.setattr(
        "niep.interfaces.socket_server.bridge_sockets", lambda *_: bridged.append(True)
    )
    instance = server(dispatcher)
    connection = Connection(send_error=BrokenPipeError())

    instance._handle_interactive_shell(
        connection, {"command": "container", "args": ["shell", "c1"]}
    )

    assert stream.closed is True
    assert bridged == []


def test_shell_bridge_error_closes_stream_and_releases_slot(monkeypatch):
    class Stream:
        closed = False

        def close(self):
            self.closed = True

    stream = Stream()
    dispatcher = Dispatcher()
    dispatcher.open_stream = lambda *_: ServiceResult(True, ResultCode.CONTAINER_SHELL, data=stream)
    monkeypatch.setattr(
        "niep.interfaces.socket_server.bridge_sockets",
        lambda *_: (_ for _ in ()).throw(RuntimeError("bridge secret")),
    )
    instance = server(dispatcher, limits=SocketLimits(session_timeout=0.1))
    connection = Connection()

    instance._handle_interactive_shell(
        connection, {"command": "container", "args": ["shell", "c1"]}
    )
    second = Connection()
    instance._handle_interactive_shell(second, {"command": "container", "args": ["shell", "c1"]})

    assert stream.closed is True
    assert response(second)["code"] != "interactive_limit"


def test_bridge_watchdog_closes_blocked_underlying_socket(monkeypatch):
    class Endpoint:
        def __init__(self):
            self.started = threading.Event()
            self.released = threading.Event()
            self.shutdown_called = False
            self.closed = False

        def sendall(self, _data):
            self.started.set()
            self.released.wait()

        def shutdown(self, _how):
            self.shutdown_called = True
            self.released.set()

        def close(self):
            self.closed = True

    class WrappedStream:
        def __init__(self, sock):
            self._sock = sock
            self.closed = False

        def close(self):
            self.closed = True

    connection = Endpoint()
    underlying = Endpoint()
    stream = WrappedStream(underlying)

    def blocked_bridge(_connection, stream, timeout=None):
        del timeout
        stream._sock.sendall(b"blocked")

    monkeypatch.setattr("niep.interfaces.socket_server.bridge_sockets", blocked_bridge)
    instance = server(limits=SocketLimits(session_timeout=0.05))

    started = time.monotonic()
    result = instance._bridge_with_timeout(connection, stream)
    elapsed = time.monotonic() - started

    assert result == (False, "session_timeout")
    assert elapsed < 0.5
    assert connection.shutdown_called is True
    assert connection.closed is True
    assert underlying.shutdown_called is True
    assert underlying.closed is True
    assert stream.closed is True


def test_interactive_slot_is_reusable_after_watchdog_timeout(monkeypatch):
    class Stream:
        __hash__ = None

        def __init__(self):
            self.release = threading.Event()
            self.closed = False

        def shutdown(self, _how):
            self.release.set()

        def close(self):
            self.closed = True
            self.release.set()

    streams = []
    dispatcher = Dispatcher()

    def open_stream(*_args):
        stream = Stream()
        streams.append(stream)
        return ServiceResult(True, ResultCode.CONTAINER_SHELL, data=stream)

    dispatcher.open_stream = open_stream

    def blocked_bridge(_connection, stream, timeout=None):
        del timeout
        stream.release.wait()

    monkeypatch.setattr("niep.interfaces.socket_server.bridge_sockets", blocked_bridge)
    instance = server(dispatcher, limits=SocketLimits(session_timeout=0.05))

    first = Connection()
    second = Connection()
    instance._handle_interactive_shell(first, {"command": "container", "args": ["shell", "c1"]})
    deadline = time.monotonic() + 1.0
    while instance._bridge_workers and time.monotonic() < deadline:
        time.sleep(0.001)
    assert instance._bridge_workers == {}
    instance._handle_interactive_shell(second, {"command": "container", "args": ["shell", "c1"]})

    assert len(streams) == 2
    assert response(first)["code"] == "container_shell"
    assert response(second)["code"] == "container_shell"
    assert all(stream.closed for stream in streams)


def test_noncooperative_bridge_holds_worker_capacity_until_thread_finishes(monkeypatch):
    release = threading.Event()
    entered = threading.Event()

    class Endpoint:
        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def noncooperative_bridge(_connection, _stream, timeout=None):
        del timeout
        entered.set()
        release.wait()

    monkeypatch.setattr("niep.interfaces.socket_server.bridge_sockets", noncooperative_bridge)
    instance = server(limits=SocketLimits(session_timeout=0.03))
    connection = Endpoint()
    stream = Endpoint()

    try:
        started = time.monotonic()
        assert instance._bridge_with_timeout(connection, stream) == (
            False,
            "session_timeout",
        )
        elapsed = time.monotonic() - started
        assert elapsed < 0.2
        assert entered.wait(1)

        workers = tuple(instance._bridge_workers.values())
        assert len(workers) == 1
        assert workers[0][0].is_alive()
        assert instance._bridge_worker_slots.acquire(blocking=False) is False

        for _ in range(4):
            assert instance._bridge_with_timeout(Endpoint(), Endpoint()) == (
                False,
                "stream_worker_limit",
            )
        assert len(instance._bridge_workers) == 1

        release.set()
        deadline = time.monotonic() + 1.0
        while instance._bridge_workers and time.monotonic() < deadline:
            time.sleep(0.001)
        assert instance._bridge_workers == {}
        assert instance._bridge_worker_slots.acquire(blocking=False) is True
        instance._bridge_worker_slots.release()
    finally:
        release.set()
        instance.close()


def test_bridge_worker_start_failure_releases_capacity(monkeypatch):
    class FailingThread:
        def __init__(self, **_kwargs):
            self.daemon = True

        def start(self):
            raise RuntimeError("thread start failed")

    monkeypatch.setattr("niep.interfaces.socket_server.threading.Thread", FailingThread)
    instance = server(limits=SocketLimits(session_timeout=0.05))

    assert instance._bridge_with_timeout(object(), object()) == (False, "stream_error")
    assert instance._bridge_workers == {}
    assert instance._bridge_worker_slots.acquire(blocking=False) is True
    instance._bridge_worker_slots.release()


def test_bridge_worker_constructor_failure_releases_preacquired_capacity(monkeypatch):
    def fail_constructor(**_kwargs):
        raise RuntimeError("thread constructor failed")

    monkeypatch.setattr("niep.interfaces.socket_server.threading.Thread", fail_constructor)
    instance = server(limits=SocketLimits(session_timeout=0.05))
    assert instance._bridge_worker_slots.acquire(blocking=False) is True

    assert instance._bridge_with_timeout(object(), object(), slot_acquired=True) == (
        False,
        "stream_error",
    )
    assert instance._bridge_workers == {}
    assert instance._bridge_worker_slots.acquire(blocking=False) is True
    instance._bridge_worker_slots.release()


def test_bridge_setup_failure_releases_capacity(monkeypatch):
    def fail_signature(_bridge):
        raise RuntimeError("signature inspection failed")

    monkeypatch.setattr("niep.interfaces.socket_server.inspect.signature", fail_signature)
    instance = server(limits=SocketLimits(session_timeout=0.05))

    assert instance._bridge_with_timeout(object(), object()) == (False, "stream_error")
    assert instance._bridge_workers == {}
    assert instance._bridge_worker_slots.acquire(blocking=False) is True
    instance._bridge_worker_slots.release()


@pytest.mark.parametrize("failure", ["event", "signature", "constructor", "start"])
@pytest.mark.parametrize("preacquired", [False, True])
def test_bridge_setup_failures_release_capacity_once(monkeypatch, failure, preacquired):
    instance = server(limits=SocketLimits(session_timeout=0.05))
    if failure == "event":
        monkeypatch.setattr(
            "niep.interfaces.socket_server.threading.Event",
            lambda: (_ for _ in ()).throw(RuntimeError("event failed")),
        )
    elif failure == "signature":
        monkeypatch.setattr(
            "niep.interfaces.socket_server.inspect.signature",
            lambda _bridge: (_ for _ in ()).throw(RuntimeError("signature failed")),
        )
    elif failure == "constructor":
        monkeypatch.setattr(
            "niep.interfaces.socket_server.threading.Thread",
            lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("constructor failed")),
        )
    else:

        class FailingThread:
            def __init__(self, **_kwargs):
                pass

            def start(self):
                raise RuntimeError("start failed")

        monkeypatch.setattr("niep.interfaces.socket_server.threading.Thread", FailingThread)

    if preacquired:
        assert instance._bridge_worker_slots.acquire(blocking=False) is True

    assert instance._bridge_with_timeout(object(), object(), slot_acquired=preacquired) == (
        False,
        "stream_error",
    )
    assert instance._bridge_workers == {}
    assert instance._bridge_worker_slots.acquire(blocking=False) is True
    instance._bridge_worker_slots.release()


def test_partial_thread_start_keeps_lease_until_worker_finishes(monkeypatch):
    real_thread = threading.Thread
    entered = threading.Event()
    release = threading.Event()
    thread_errors = []

    class PartialThread(real_thread):
        def start(self):
            super().start()
            raise RuntimeError("partial start")

    class Endpoint:
        def shutdown(self, _how):
            pass

        def close(self):
            pass

    def blocked_bridge(_connection, _stream, timeout=None):
        del timeout
        entered.set()
        release.wait()

    def capture_thread_error(args):
        thread_errors.append(args)

    monkeypatch.setattr("niep.interfaces.socket_server.bridge_sockets", blocked_bridge)
    monkeypatch.setattr("niep.interfaces.socket_server.threading.Thread", PartialThread)
    monkeypatch.setattr("niep.interfaces.socket_server.threading.excepthook", capture_thread_error)
    instance = server(limits=SocketLimits(session_timeout=1.0))

    try:
        result = instance._bridge_with_timeout(Endpoint(), Endpoint())
        assert result == (False, "stream_error")
        assert entered.wait(1)
        assert len(instance._bridge_workers) == 1
        assert instance._bridge_worker_slots.acquire(blocking=False) is False
        assert thread_errors == []

        release.set()
        deadline = time.monotonic() + 1.0
        while instance._bridge_workers and time.monotonic() < deadline:
            time.sleep(0.001)
        assert instance._bridge_workers == {}
        assert instance._bridge_worker_slots.acquire(blocking=False) is True
        instance._bridge_worker_slots.release()
    finally:
        release.set()
        instance.close()


def test_close_terminates_registered_interactive_stream(monkeypatch):
    class Stream:
        __hash__ = None

        def __init__(self):
            self.started = threading.Event()
            self.release = threading.Event()
            self.closed = False

        def shutdown(self, _how):
            self.release.set()

        def close(self):
            self.closed = True
            self.release.set()

    stream = Stream()
    dispatcher = Dispatcher()
    dispatcher.open_stream = lambda *_: ServiceResult(True, ResultCode.CONTAINER_SHELL, data=stream)

    def blocked_bridge(_connection, stream, timeout=None):
        del timeout
        stream.started.set()
        stream.release.wait()

    monkeypatch.setattr("niep.interfaces.socket_server.bridge_sockets", blocked_bridge)
    instance = server(dispatcher, limits=SocketLimits(session_timeout=5.0))
    connection = Connection()
    worker = threading.Thread(
        target=instance._handle_interactive_shell,
        args=(connection, {"command": "container", "args": ["shell", "c1"]}),
    )
    worker.start()
    assert stream.started.wait(1)

    instance.close()
    worker.join(timeout=1)

    assert not worker.is_alive()
    assert stream.closed is True
    assert instance._interactive_streams == {}


def test_runtime_bridge_transfers_data_and_returns_on_eof():
    left, right = socket.socketpair()
    result = []
    worker = threading.Thread(target=lambda: result.append(bridge_sockets(left, right, 1.0)))
    worker.start()
    try:
        left.sendall(b"hello")
        assert right.recv(5) == b"hello"
        left.shutdown(socket.SHUT_WR)
        worker.join(timeout=1)
        assert not worker.is_alive()
        assert result == [True]
    finally:
        left.close()
        right.close()


def test_runtime_terminal_bridge_supports_eof_without_deadline():
    input_read, input_write = os.pipe()
    output_read, output_write = os.pipe()
    left, right = socket.socketpair()
    try:
        right.close()
        os.close(input_write)
        bridge_terminal(left, input_fd=input_read, output_fd=output_write, timeout=None)
    finally:
        left.close()
        os.close(input_read)
        os.close(output_read)
        os.close(output_write)


def test_parent_validation_rejects_writable_or_symlinked_parent(tmp_path: Path):
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir()
    unsafe.chmod(0o775)
    instance = server()
    with pytest.raises(RuntimeError):
        instance._validate_parent(unsafe)

    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(RuntimeError):
        instance._validate_parent(link)


def test_bind_failure_without_inode_proof_preserves_the_socket_path(tmp_path, monkeypatch):
    socket_path = tmp_path / "niep.sock"
    instance = server(socket_path=str(socket_path), secure_parent=False)
    real_stat = os.stat
    calls = 0

    def flaky_stat(path, *args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("metadata probe failed")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr("niep.interfaces.socket_server.os.stat", flaky_stat)
    monkeypatch.setattr("niep.interfaces.socket_server.os.chown", lambda *_: None)
    with pytest.raises(OSError, match="metadata probe failed"):
        instance._prepare_socket()
    assert socket_path.exists()


def test_bind_failure_after_inode_capture_removes_only_our_socket(tmp_path, monkeypatch):
    socket_path = tmp_path / "niep.sock"
    instance = server(socket_path=str(socket_path), secure_parent=False)
    monkeypatch.setattr(
        "niep.interfaces.socket_server.os.chown",
        lambda *_: (_ for _ in ()).throw(PermissionError("chown failed")),
    )
    with pytest.raises(PermissionError, match="chown failed"):
        instance._prepare_socket()
    assert not socket_path.exists()


def test_close_does_not_unlink_a_replaced_socket_inode(tmp_path):
    first = tmp_path / "first.sock"
    second = tmp_path / "second.sock"
    # A socket path replacement is represented by two distinct inodes.
    first_listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    first_listener.bind(str(first))
    identity = os.stat(first)
    first_listener.close()
    replacement = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    replacement.bind(str(second))
    os.rename(second, first)
    instance = server(socket_path=str(first), secure_parent=False)
    instance._bound_identity = (identity.st_dev, identity.st_ino)
    instance.close()
    assert first.exists()
    replacement.close()
