#!/usr/bin/env python3
import argparse
from os.path import abspath
from sys import path


ROOT = '/'.join(abspath(__file__).split('/')[:-2])
path.insert(0, ROOT + '/TOPO-MAN')
path.insert(0, ROOT + '/VEM')

from SocketServer import NIEPSocketServer


def main():
    parser = argparse.ArgumentParser(description='Run the NIEP local command daemon.')
    parser.add_argument('--socket', default='/tmp/niep.sock', help='Unix socket path')
    args = parser.parse_args()

    server = NIEPSocketServer(args.socket)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.close()


if __name__ == '__main__':
    main()
