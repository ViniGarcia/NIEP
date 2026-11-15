"""Exercise the real async collector against local HTTP endpoints, without Mininet."""
import asyncio
from pathlib import Path
import runpy
import time

import pytest


PROBE = runpy.run_path(str(Path(__file__).resolve().parents[3] /
                           'benchmarks/startup/http-probe.py'))


def test_slow_endpoint_does_not_block_other_observations():
    async def scenario():
        slow_started = asyncio.Event()
        fast_started = asyncio.Event()

        async def serve(reader, writer):
            try:
                await reader.readuntil(b'\r\n\r\n')
                address = writer.get_extra_info('sockname')[0]
                if address == '127.0.0.3':
                    await reader.read()  # Never responds; the collector must close it on timeout.
                    return
                if address == '127.0.0.1':
                    slow_started.set()
                    await fast_started.wait()
                    await asyncio.sleep(.05)
                else:
                    await slow_started.wait()
                    fast_started.set()
                writer.write(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok')
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, '0.0.0.0', 0)
        async with server:
            start = time.perf_counter() - .1  # Includes time already spent in topoup.
            records = await PROBE['collect'](3, '127.0.0.1', start, .5, .01,
                                              port=server.sockets[0].getsockname()[1])
        assert [r['index'] for r in records] == [0, 1, 2]
        assert all(r['status'] == 'ready' and r['ready_ms'] >= 100 for r in records[:2])
        assert records[1]['ready_ms'] < records[0]['ready_ms']
        assert records[2]['status'] == 'timeout'
        assert records[2]['ready_ms'] == ''

    asyncio.run(scenario())


@pytest.mark.parametrize('status,body', [(200, b'wrong'), (200, b'ok!'), (503, b'ok')])
def test_only_exact_success_is_ready_and_requests_share_original_deadline(status, body):
    async def scenario():
        attempts = []

        async def serve(reader, writer):
            try:
                await reader.readuntil(b'\r\n\r\n')
                attempts.append(time.perf_counter())
                writer.write(f'HTTP/1.0 {status} Test\r\nContent-Length: {len(body)}\r\n\r\n'
                             .encode() + body)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        async with server:
            start = time.perf_counter() - .1
            records = await asyncio.wait_for(PROBE['collect'](
                1, '127.0.0.1', start, .2, .01,
                port=server.sockets[0].getsockname()[1]), .18)
        assert len(attempts) >= 2  # Invalid responses are retried.
        assert records[0]['status'] == 'timeout'
        assert records[0]['ready_ms'] == ''
        assert records[0]['error']

    asyncio.run(scenario())


def test_expired_deadline_never_connects(monkeypatch):
    async def unexpected_connection(*_args):
        pytest.fail('must not connect after the deadline')

    monkeypatch.setattr(asyncio, 'open_connection', unexpected_connection)
    records = asyncio.run(PROBE['collect'](2, '127.0.0.1', time.perf_counter() - 2, 1, 0))
    assert all(r['status'] == 'timeout' for r in records)


def test_runner_cancellation_closes_pending_connections(tmp_path):
    async def scenario():
        marker = tmp_path / 'active'
        marker.touch()
        connected = asyncio.Event()
        closed = asyncio.Event()

        async def serve(reader, writer):
            try:
                await reader.readuntil(b'\r\n\r\n')
                connected.set()
                assert await reader.read() == b''
                closed.set()
            finally:
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        async with server:
            task = asyncio.create_task(PROBE['collect'](
                1, '127.0.0.1', time.perf_counter(), 180, 30,
                port=server.sockets[0].getsockname()[1], alive_file=marker))
            await asyncio.wait_for(connected.wait(), 1)
            marker.unlink()
            assert await asyncio.wait_for(task, 1) == []
            await asyncio.wait_for(closed.wait(), 1)

    asyncio.run(scenario())
