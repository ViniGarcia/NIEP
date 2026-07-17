import json
import os
import socket

from Command import CommandDispatcher
from TerminalSession import bridge_sockets


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
        os.chmod(self.socket_path, 0o660)
        self.socket.listen(5)

    def _handle_connection(self, connection):
        request = self._read_request(connection)
        if self._is_interactive_shell(request):
            self._handle_interactive_shell(connection, request)
            return
        response = self.handle_request(request)
        connection.sendall((json.dumps(response) + '\n').encode('utf-8'))

    def _is_interactive_shell(self, request):
        args = request.get('args', [])
        return request.get('command') == 'container' and len(args) >= 2 and args[0] == 'shell'

    def _handle_interactive_shell(self, connection, request):
        args = request.get('args', [])
        container_id = args[1]
        command = args[2:] or ['/bin/sh']
        result = self.dispatcher.container.open_shell(container_id, command)
        response = result.to_dict()
        response.pop('data', None)
        connection.sendall((json.dumps(response) + '\n').encode('utf-8'))
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
            return {}
        return json.loads(payload)

    def handle_request(self, request):
        command = request.get('command', '')
        args = request.get('args', [])
        result = self.dispatcher.dispatch(command, args)
        return result.to_dict()
