from __future__ import annotations

import json

import pytest

from niep.application.commands import CommandProtocolError, CommandRequest
from niep.interfaces.niepctl import MAX_REQUEST_BYTES, send_request
from niep.interfaces.socket_server import MAX_REQUEST_BYTES as SERVER_MAX_REQUEST_BYTES
from niep.interfaces.socket_server import SocketLimits


pytestmark = pytest.mark.contract


def test_protocol_and_client_share_the_64_kib_frame_contract():
    assert MAX_REQUEST_BYTES == SERVER_MAX_REQUEST_BYTES == 64 * 1024
    assert SocketLimits().max_request_bytes == MAX_REQUEST_BYTES


@pytest.mark.parametrize(
    "payload",
    [
        {"protocol": "other", "version": 1, "command": "status"},
        {"protocol": "niep.command", "version": 0, "command": "status"},
        {"protocol": "niep.command", "version": 1, "command": "status", "extra": 1},
        {"protocol": "niep.command", "version": 1, "command": "status", "args": [1]},
    ],
)
def test_protocol_rejects_version_types_and_unknown_fields(payload):
    with pytest.raises(CommandProtocolError):
        CommandRequest.from_dict(payload)


def test_legacy_request_is_accepted_only_as_a_normalized_v1_request():
    request = CommandRequest.from_dict({"command": "status"})
    assert request.protocol == "niep.command"
    assert request.version == 1
    assert request.request_id
    assert request.args == ()


def test_client_rejects_oversized_payload_before_connecting(monkeypatch):
    class ExplodingSocket:
        def connect(self, _path):
            raise AssertionError("oversized payload connected")

    monkeypatch.setattr("niep.interfaces.niepctl.socket.socket", lambda *_: ExplodingSocket())
    with pytest.raises(ValueError, match="64 KiB"):
        send_request("/run/niep.sock", "status", ["x" * (MAX_REQUEST_BYTES + 1)])


def test_command_request_json_has_no_runtime_values():
    request = CommandRequest("status", options={"safe": ["value"]})
    payload = json.loads(request.to_json())
    assert set(payload) == {"protocol", "version", "request_id", "command", "args", "options"}


@pytest.mark.parametrize(
    "response_chunks",
    [
        [b'{"ok":true}'],
        [b'{"ok":true}\ntrailing'],
    ],
)
def test_client_requires_one_complete_response_frame(monkeypatch, response_chunks):
    class Client:
        def __init__(self):
            self.chunks = list(response_chunks)

        def settimeout(self, _timeout):
            pass

        def connect(self, _path):
            pass

        def sendall(self, _payload):
            pass

        def recv(self, _size):
            return self.chunks.pop(0) if self.chunks else b""

        def close(self):
            pass

    monkeypatch.setattr("niep.interfaces.niepctl.socket.socket", lambda *_: Client())
    with pytest.raises(RuntimeError):
        send_request("/run/niep.sock", "status", [])
