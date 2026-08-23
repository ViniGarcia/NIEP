import grp
import json
import os
import socket

from niep.application.command import CommandDispatcher, _public_result
from niep.application.commands import CommandProtocolError, CommandRequest, CommandResponse
from niep.application.stream import bridge_sockets


SOCKET_GROUP = 'niep'


class NIEPSocketServer:
    def __init__(self, socket_path='/run/niep.sock', dispatcher=None):
        self.socket_path = socket_path
        self.dispatcher = dispatcher or CommandDispatcher()
        self.socket = None

    def serve_forever(self):
        self._prepare_socket()
        try:
            while True:
                connection, _ = self.socket.accept()
                with connection:
                    self._handle_connection(connection)
        finally:
            self.close()

    def close(self):
        if self.socket is not None:
            self.socket.close()
            self.socket = None
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

    def _prepare_socket(self):
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous_umask = os.umask(0o177)
        try:
            self.socket.bind(self.socket_path)
        finally:
            os.umask(previous_umask)
        socket_group = grp.getgrnam(SOCKET_GROUP)
        os.chown(self.socket_path, 0, socket_group.gr_gid)
        os.chmod(self.socket_path, 0o660)
        self.socket.listen(5)

    def _handle_connection(self, connection):
        try:
            request = self._read_request(connection)
        except (CommandProtocolError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            response = CommandResponse.failure("invalid", getattr(exc, "code", "invalid_request"), str(exc))
            connection.sendall((json.dumps(response.to_dict()) + '\n').encode('utf-8'))
            return
        try:
            if self._is_interactive_shell(request):
                self._handle_interactive_shell(connection, request)
                return
        except CommandProtocolError as exc:
            response = CommandResponse.failure("invalid", exc.code, str(exc))
            connection.sendall((json.dumps(response.to_dict()) + '\n').encode('utf-8'))
            return
        response = self.handle_request(request)
        connection.sendall((json.dumps(response) + '\n').encode('utf-8'))

    def _is_interactive_shell(self, request):
        args = request.get('args', [])
        if not isinstance(args, (list, tuple)) or any(not isinstance(arg, str) for arg in args):
            return False
        return request.get('command') == 'container' and len(args) >= 2 and args[0] == 'shell'

    def _handle_interactive_shell(self, connection, request):
        request = CommandRequest.from_dict(request)
        args = request.args
        container_id = args[1]
        command = args[2:] or ['/bin/sh']
        result = self.dispatcher.open_stream("container", ("shell", container_id, *command))
        response = CommandResponse.from_result(request, result)
        connection.sendall((json.dumps(response.to_dict()) + '\n').encode('utf-8'))
        if not result.ok:
            return

        stream = result.data
        try:
            bridge_sockets(connection, stream)
        finally:
            try:
                stream.close()
            except Exception:
                pass

    def _read_request(self, connection):
        chunks = []
        while True:
            chunk = connection.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b'\n' in chunk:
                break
        payload = b''.join(chunks).decode('utf-8').strip()
        if not payload:
            raise CommandProtocolError("empty command request")
        request = json.loads(payload)
        if not isinstance(request, dict):
            raise CommandProtocolError("command request must be a JSON object")
        return request

    def handle_request(self, request):
        if hasattr(self.dispatcher, "dispatch_request"):
            response = self.dispatcher.dispatch_request(request)
            return response.to_dict()
        # Compatibility for external dispatcher doubles still goes through
        # the same validated and sanitized response envelope.
        try:
            normalized = CommandRequest.from_dict(request)
            result = _public_result(self.dispatcher.dispatch(normalized.command, normalized.args))
            return CommandResponse.from_result(normalized, result).to_dict()
        except (CommandProtocolError, TypeError) as exc:
            return CommandResponse.failure(
                "invalid",
                getattr(exc, "code", "invalid_request"),
                str(exc),
            ).to_dict()
