"""Record actual runtime starts and HTTP readiness in the same topology trial."""
from datetime import datetime, timezone
import math
import threading
import time
import uuid

from niep.domain.result import ResultCode, ServiceResult
from niep.runtime.start_events import capture_starts
from niep.runtime.startup_probe import container_probe, vm_probe


class Ticket:
    def __init__(self, kind, resource, timeout, interval, probe_factory):
        ident = resource.name() if kind == 'vm' else resource.name
        self.row = dict(kind=kind, id=ident, runtime_id=(resource.UUIDString() if kind == 'vm' else resource.id),
                        started_at='', start_call_ms=None, runtime_ready_ms=None,
                        probe_path='libvirt_management_dhcp' if kind == 'vm' else 'container_loopback',
                        status='pending', error='')
        self.timeout, self.interval = timeout, interval
        self.lock = threading.Lock()
        self.cancelled = threading.Event()
        self.armed = threading.Event()
        try:
            self.probe = probe_factory(resource)
        except Exception as exc:
            self.probe = None
            self.row.update(status='probe_failed', error=str(exc))
        self.thread = threading.Thread(target=self.poll, daemon=True)
        self.thread.start()

    def begin(self):
        self.row['started_at'] = datetime.now(timezone.utc).isoformat()
        self.start_ns = time.perf_counter_ns()
        self.armed.set()

    def finished(self):
        with self.lock:
            self.row['start_call_ms'] = round((time.perf_counter_ns() - self.start_ns) / 1e6, 3)

    def failed(self, exc):
        self.cancelled.set()
        with self.lock:
            self.row.update(status='start_failed', error=str(exc),
                            start_call_ms=round((time.perf_counter_ns() - self.start_ns) / 1e6, 3))

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.row['status'] == 'pending':
                self.row.update(status='cancelled', error='Topology stopped before HTTP readiness')

    def snapshot(self):
        with self.lock:
            return dict(self.row)

    def poll(self):
        self.armed.wait()
        if self.probe is None:
            return
        last_error = ''
        while not self.cancelled.is_set():
            remaining = self.timeout - (time.perf_counter_ns() - self.start_ns) / 1e9
            if remaining <= 0:
                with self.lock:
                    if not self.cancelled.is_set():
                        self.row.update(status='timeout', error=last_error or 'HTTP readiness timeout')
                return
            try:
                ready_ns = self.probe(min(.3, remaining))
                if ready_ns is not None:
                    with self.lock:
                        if not self.cancelled.is_set():
                            self.row.update(status='ready', error='',
                                            runtime_ready_ms=round((ready_ns - self.start_ns) / 1e6, 3))
                    return
            except Exception as exc:
                last_error = str(exc)
            self.cancelled.wait(min(self.interval, remaining))


class StartupTimingService:
    def __init__(self, session, *, vm_factory=vm_probe, container_factory=container_probe):
        self.session = session
        self.factories = {'vm': vm_factory, 'container': container_factory}
        self.lock = threading.Lock()
        self.tickets = []
        self.enabled = False
        self.capturing = False
        self.capture_id = None
        self.timeout, self.interval = 180., .1

    def prepare(self, kind, resource):
        ticket = Ticket(kind, resource, self.timeout, self.interval, self.factories[kind])
        with self.lock:
            self.tickets.append(ticket)
        return ticket

    def cancel(self):
        with self.lock:
            for ticket in self.tickets:
                ticket.cancel()

    def up(self, args, callback):
        with self.lock:
            active = not args and self.enabled
            if active:
                self.enabled = False  # One arm applies to exactly one topoup.
                self.capturing = True
        if not active:
            return callback(args)
        try:
            with capture_starts(self):
                result = callback(args)
            if not result.ok:
                self.cancel()
            return result
        except BaseException:
            self.cancel()
            raise
        finally:
            self.capturing = False

    def stop(self, args, callback):
        if not args:
            self.cancel()
        return callback(args)

    def handle(self, args):
        if len(args) == 3 and args[0] == 'arm':
            try:
                timeout, interval = map(float, args[1:])
                if (not all(math.isfinite(v) for v in (timeout, interval))
                        or not 0 < interval <= 10 or not 0 < timeout <= 3600):
                    raise ValueError
            except ValueError:
                return ServiceResult(ok=False, code=ResultCode.INVALID_COMMAND_ARGS,
                                     message='Expected timeout (0,3600] and interval (0,10] seconds')
            if self.capturing or self.session.is_up():
                return ServiceResult(ok=False, code=ResultCode.INVALID_COMMAND_ARGS,
                                     message='Arm startup timing before topoup')
            self.cancel()
            with self.lock:
                self.tickets = []
                self.timeout, self.interval = timeout, interval
                self.capture_id = uuid.uuid4().hex
                self.enabled = True
        elif args == ('disable',):
            self.cancel()
            self.enabled = False
        elif args != ('snapshot',):
            return ServiceResult(ok=False, code=ResultCode.INVALID_COMMAND_ARGS,
                                 message='startup-timing expects arm TIMEOUT INTERVAL, snapshot or disable')
        with self.lock:
            rows = [t.snapshot() for t in self.tickets]
        return ServiceResult(ok=True, code=ResultCode.STARTUP_TIMING, data={
            'capture_id': self.capture_id, 'resources': rows,
            'pending': sum(row['status'] == 'pending' for row in rows)})
