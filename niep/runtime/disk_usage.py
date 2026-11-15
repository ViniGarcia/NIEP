"""Read storage owned by runtime instances, excluding shared base images."""
from pathlib import Path


def vm_disk_usage(vm):
    disk = Path(vm.IMAGE_STORE.instance_disk_path(vm.ID, vm.DISK))
    try:
        info = disk.stat()
    except FileNotFoundError:
        if not vm.VM_EXIST:
            return {'disk_bytes': 0, 'file_bytes': 0, 'source': 'host_allocated_blocks'}
        raise
    return {'disk_bytes': info.st_blocks * 512, 'file_bytes': info.st_size,
            'source': 'host_allocated_blocks'}


def container_disk_usage(container):
    handle = container.CONTAINER
    if handle is None:
        return {'disk_bytes': 0, 'source': 'docker_writable_layer'}
    # SDK inspect_container does not expose the Engine's size option. The list
    # endpoint does, and an exact container-ID filter limits the expensive scan.
    entries = handle.client.api.containers(all=True, size=True, filters={'id': [handle.id]})
    entry = next((row for row in entries if row['Id'] == handle.id), None)
    if entry is None:
        raise RuntimeError('Container no longer exists')
    size = entry.get('SizeRw')
    if size is None or size < 0:
        raise RuntimeError('Docker storage driver did not report writable-layer size')
    return {'disk_bytes': size, 'source': 'docker_writable_layer'}
