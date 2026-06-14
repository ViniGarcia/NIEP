#!/usr/bin/env python3
import argparse
import json
import socket


def send_request(socket_path, command, args):
    payload = json.dumps({'command': command, 'args': args}) + '\n'
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        client.connect(socket_path)
        client.sendall(payload.encode('utf-8'))
        chunks = []
        while True:
            chunk = client.recv(4096)
            if not chunk:
                break
            chunks.append(chunk)
            if b'\n' in chunk:
                break
    finally:
        client.close()
    return json.loads(b''.join(chunks).decode('utf-8'))


def main():
    parser = argparse.ArgumentParser(description='Send a command to the NIEP local daemon.')
    parser.add_argument('--socket', default='/tmp/niep.sock', help='Unix socket path')
    parser.add_argument('--json', action='store_true', help='Print the complete JSON response')
    parser.add_argument('command')
    parser.add_argument('args', nargs='*')
    args = parser.parse_args()

    response = send_request(args.socket, args.command, args.args)
    if args.json:
        print(json.dumps(response, indent=2, sort_keys=True))
    elif response.get('data') is not None:
        print(response.get('data'))
    elif response.get('message'):
        print(response.get('message'))
    else:
        print(response.get('code'))

    return 0 if response.get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
