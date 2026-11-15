"""Session-scoped resource sampling without sleeps or background workers."""
from datetime import datetime, timezone
import threading
import time

from niep.domain.result import ResultCode, ServiceResult
from niep.runtime.metrics import container_counters, daemon_counters, vm_counters


class MetricsService:
    def __init__(self, session, *, vm_reader=vm_counters, container_reader=container_counters,
                 daemon_reader=daemon_counters, clock=time.monotonic):
        self.session = session
        self.readers = {'vm': vm_reader, 'container': container_reader}
        self.daemon_reader = daemon_reader
        self.clock = clock
        self.previous = {}
        self.lock = threading.Lock()

    def sample(self, key, reader):
        row = {'kind': key[0], 'id': key[1], 'cpu_percent': None,
               'memory_bytes': None, 'error': None}
        try:
            raw = reader()
            now = self.clock()
            row.update({k: v for k, v in raw.items() if k != 'identity'})
            counter = raw.get('cpu_time_ns')
            previous = self.previous.get(key)
            identity = raw.get('identity')
            if raw['state'] != 'running':
                row['cpu_percent'] = 0.0
                self.previous.pop(key, None)
            elif counter is not None:
                if (previous and previous[0] == identity and counter >= previous[2]
                        and now > previous[1]):
                    row['cpu_percent'] = round((counter - previous[2]) /
                                               ((now - previous[1]) * 1_000_000_000) * 100, 3)
                    row['sample_interval_seconds'] = round(now - previous[1], 6)
                self.previous[key] = (identity, now, counter)
            else:
                self.previous.pop(key, None)
        except Exception as exc:
            self.previous.pop(key, None)
            row.update(state='unavailable', error=str(exc))
        return row

    @staticmethod
    def aggregate(rows):
        return {'resources': len(rows),
                'cpu_percent': round(sum(r['cpu_percent'] or 0 for r in rows), 3),
                'memory_bytes': sum(r['memory_bytes'] or 0 for r in rows),
                'cpu_samples': sum(r['cpu_percent'] is not None for r in rows),
                'memory_samples': sum(r['memory_bytes'] is not None for r in rows),
                'partial': any(r['cpu_percent'] is None or r['memory_bytes'] is None for r in rows)}

    def snapshot(self, args=()):
        if args:
            return ServiceResult(ok=False, code=ResultCode.INVALID_COMMAND_ARGS,
                                 message='stats expects no arguments')
        with self.lock:
            resources = []
            for kind, group in (('vm', 'vms'), ('container', 'containers')):
                for ident in self.session.resource_ids(group):
                    def read(kind=kind, ident=ident):
                        return self.readers[kind](self.session.get_resource(kind, ident))
                    resources.append(self.sample((kind, ident), read))
            daemon = self.sample(('daemon', 'niepd'), self.daemon_reader)
            active = {(r['kind'], r['id']) for r in resources + [daemon]}
            self.previous = {k: v for k, v in self.previous.items() if k in active}
            totals = {group: self.aggregate([r for r in resources if r['kind'] == kind])
                      for kind, group in (('vm', 'vms'), ('container', 'containers'))}
            totals['workloads'] = self.aggregate(resources)
            totals['with_daemon'] = self.aggregate(resources + [daemon])
            return ServiceResult(ok=True, code=ResultCode.STATS, data={
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'cpu_percent_per_core': 100, 'resources': resources,
                'daemon': daemon, 'totals': totals})
