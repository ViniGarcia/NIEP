#!/usr/bin/env python3
import argparse



from niep.interfaces.socket_server import NIEPSocketServer


def main():
    parser = argparse.ArgumentParser(description='Run the NIEP local command daemon.')
    parser.add_argument('--socket', default='/run/niep.sock', help='Unix socket path')
    args = parser.parse_args()

    server = NIEPSocketServer(args.socket)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.close()


if __name__ == '__main__':
    main()
