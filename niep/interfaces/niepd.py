#!/usr/bin/env python3
import argparse
import logging

from niep.interfaces.socket_server import NIEPSocketServer


def main():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Run the NIEP local command daemon.")
    parser.add_argument("--socket", default="/run/niep.sock", help="Unix socket path")
    parser.add_argument("--socket-group", default="niep", help="Authorized Unix group")
    parser.add_argument(
        "--read-timeout", type=float, default=5.0, help="Request read timeout in seconds"
    )
    parser.add_argument(
        "--session-timeout",
        type=float,
        default=300.0,
        help="Interactive session timeout in seconds",
    )
    parser.add_argument("--max-interactive-sessions", type=int, default=1)
    parser.add_argument("--max-connection-workers", type=int, default=32)
    parser.add_argument("--max-request-bytes", type=int, default=64 * 1024)
    parser.add_argument("--max-response-bytes", type=int, default=64 * 1024)
    args = parser.parse_args()

    server = NIEPSocketServer(
        args.socket,
        group_name=args.socket_group,
        read_timeout=args.read_timeout,
        session_timeout=args.session_timeout,
        max_interactive_sessions=args.max_interactive_sessions,
        max_connection_workers=args.max_connection_workers,
        max_request_bytes=args.max_request_bytes,
        max_response_bytes=args.max_response_bytes,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.close()


if __name__ == "__main__":
    main()
