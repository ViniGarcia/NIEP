"""Storage snapshot for the active session's VMs and containers."""
from datetime import datetime, timezone

from niep.domain.result import ResultCode, ServiceResult
from niep.runtime.disk_usage import container_disk_usage, container_image_usage, vm_disk_usage


class DiskUsageService:
    def __init__(self, session, *, vm_reader=vm_disk_usage, container_reader=container_disk_usage,
                 image_reader=container_image_usage):
        self.session = session
        self.readers = {'vm': vm_reader, 'container': container_reader}
        self.image_reader = image_reader

    @staticmethod
    def total(rows):
        return {'disk_bytes': sum(row['disk_bytes'] or 0 for row in rows),
                'resources': len(rows),
                'measured_resources': sum(row['disk_bytes'] is not None for row in rows),
                'partial': any(row['disk_bytes'] is None for row in rows)}

    def snapshot(self, args=()):
        if args:
            return ServiceResult(ok=False, code=ResultCode.INVALID_COMMAND_ARGS,
                                 message='disk-usage expects no arguments')
        rows = []
        image_cache = {}
        for kind, group in (('vm', 'vms'), ('container', 'containers')):
            for ident in self.session.resource_ids(group):
                row = dict(kind=kind, id=ident, disk_bytes=None, error=None)
                try:
                    row.update(self.readers[kind](self.session.get_resource(kind, ident)))
                except Exception as exc:
                    row['error'] = str(exc)
                if kind == 'container':
                    row.update(image_id=None, image_bytes=None, image_source=None, image_error=None)
                    try:
                        row.update(self.image_reader(self.session.get_resource(kind, ident), image_cache))
                    except Exception as exc:
                        row['image_error'] = str(exc)
                rows.append(row)
        totals = {group: self.total([r for r in rows if r['kind'] == kind])
                  for kind, group in (('vm', 'vms'), ('container', 'containers'))}
        totals['workloads'] = self.total(rows)
        return ServiceResult(ok=True, code=ResultCode.DISK_USAGE, data={
            'timestamp': datetime.now(timezone.utc).isoformat(), 'resources': rows,
            'totals': totals, 'scope': 'private_vm_disks_and_container_writable_layers'})
