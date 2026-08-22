import os
import select
import sys
import termios
import tty
from contextlib import contextmanager


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


def bridge_terminal(stream, input_fd=None, output_fd=None, initial_output=b""):
    input_fd = sys.stdin.fileno() if input_fd is None else input_fd
    output_fd = sys.stdout.fileno() if output_fd is None else output_fd
    stream = socket_object(stream)

    if initial_output:
        os.write(output_fd, initial_output)

    with raw_terminal(input_fd):
        input_open = True
        while True:
            sources = [stream]
            if input_open:
                sources.append(input_fd)
            readable, _, _ = select.select(sources, [], [])
            if stream in readable:
                data = receive(stream)
                if not data:
                    break
                os.write(output_fd, data)
            if input_open and input_fd in readable:
                data = os.read(input_fd, 65536)
                if not data:
                    input_open = False
                    try:
                        stream.shutdown(1)
                    except OSError:
                        pass
                    continue
                send(stream, data)


def bridge_sockets(client, stream):
    stream = socket_object(stream)
    peers = (client, stream)
    while True:
        readable, _, _ = select.select(peers, [], [])
        for source in readable:
            data = receive(source)
            if not data:
                return
            target = stream if source is client else client
            send(target, data)
