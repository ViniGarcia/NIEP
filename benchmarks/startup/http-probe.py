#!/usr/bin/env python3
"""Concurrent HTTP readiness collector, executed once inside Mininet h1."""
import argparse
import asyncio
import http.client
import io
import ipaddress
import json
import math
from pathlib import Path
import time


class ResponseSocket:
    def __init__(self, data):
        self.data = data

    def makefile(self, *_args):
        return io.BytesIO(self.data)


async def request(address, port):
    reader, writer = await asyncio.open_connection(address, port)
    try:
        writer.write((f'GET /health HTTP/1.0\r\nHost: {address}\r\n'
                      'Connection: close\r\n\r\n').encode('ascii'))
        await writer.drain()
        data = bytearray()
        while True:
            chunk = await reader.read(min(4096, 65537 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
            if len(data) > 65536:
                raise ValueError('HTTP response exceeds 64 KiB')
        response = http.client.HTTPResponse(ResponseSocket(bytes(data)))
        response.begin()
        if response.status != 200 or response.read(3) != b'ok':
            raise ValueError(f'Expected HTTP 200 with exact body ok; got HTTP {response.status}')
        return time.perf_counter()
    finally:
        writer.close()
        await writer.wait_closed()


async def probe(index, address, start, deadline, interval, port):
    error = 'Deadline reached before HTTP observation'
    while (remaining := deadline - time.perf_counter()) > 0:
        try:
            observed = await asyncio.wait_for(request(address, port), min(.3, remaining))
            if observed <= deadline:
                return dict(index=index, ready_ms=round((observed - start) * 1000, 3),
                            status='ready', error='')
        except (OSError, ValueError, http.client.HTTPException, asyncio.TimeoutError) as exc:
            error = str(exc) or type(exc).__name__
        await asyncio.sleep(min(interval, max(0, deadline - time.perf_counter())))
    return dict(index=index, ready_ms='', status='timeout', error=error)


async def collect(count, first_address, start, timeout, interval, port=8080, alive_file=None):
    first = ipaddress.IPv4Address(first_address)
    # All tasks share the runner's original start and deadline. No worker queue:
    # an unresponsive endpoint must not delay observations of other endpoints.
    tasks = [asyncio.create_task(probe(i, str(first + i), start, start + timeout, interval, port))
             for i in range(count)]

    async def watch_runner():
        while Path(alive_file).exists():
            await asyncio.sleep(.05)
        for task in tasks:
            task.cancel()

    watcher = asyncio.create_task(watch_runner()) if alive_file is not None else None
    try:
        return await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        # The runner removes its marker on interruption, before requesting cleanup.
        await asyncio.gather(*tasks, return_exceptions=True)
        return []
    finally:
        if watcher is not None:
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('count', type=int)
    parser.add_argument('first_address')
    parser.add_argument('start', type=float)
    parser.add_argument('timeout', type=float)
    parser.add_argument('interval', type=float)
    parser.add_argument('alive_file')
    args = parser.parse_args()
    if (args.count < 1 or not all(math.isfinite(v) for v in
                                 (args.start, args.timeout, args.interval))
            or args.timeout <= 0 or args.interval < 0):
        parser.error('count/timeout must be positive and times finite; interval must be nonnegative')
    print(json.dumps(asyncio.run(collect(args.count, args.first_address, args.start,
                                        args.timeout, args.interval, alive_file=args.alive_file))))


if __name__ == '__main__':
    main()
