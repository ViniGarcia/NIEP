"""Read private instance allocation and separate shared container image estimates."""
from pathlib import Path
import os
import re
import stat


def allocated_tree_bytes(root):
    """Count allocated blocks once per inode, including directories and symlinks.

    Never follow symlinks or cross filesystems. Let traversal errors propagate:
    a partial walk must not masquerade as a complete measurement.
    """
    root = Path(root)
    root_info = root.lstat()
    if not stat.S_ISDIR(root_info.st_mode):
        raise OSError('Writable layer is not a directory')
    seen = set()
    pending = [root]
    total = 0
    while pending:
        path = pending.pop()
        info = path.lstat()
        if info.st_dev != root_info.st_dev:
            raise OSError('Writable layer contains another filesystem')
        inode = (info.st_dev, info.st_ino)
        if inode in seen:
            continue
        seen.add(inode)
        total += info.st_blocks * 512
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as entries:
                pending.extend(Path(entry.path) for entry in entries)
    return total


def container_upper_dir(info):
    """Locate the private OverlayFS layer for classic and containerd Engines."""
    upper = ((info.get('GraphDriver') or {}).get('Data') or {}).get('UpperDir')
    if upper:
        return upper
    # The containerd image store does not expose GraphDriver.Data. Its running
    # container's root mount still identifies the writable snapshot, without
    # guessing Docker/containerd data roots or counting the merged image.
    pid = (info.get('State') or {}).get('Pid')
    if type(pid) is not int or pid <= 0:
        return None
    for line in Path(f'/proc/{pid}/mountinfo').read_text().splitlines():
        fields = line.split()
        if len(fields) < 10 or fields[4] != '/' or '-' not in fields:
            continue
        separator = fields.index('-')
        if len(fields) <= separator + 3 or fields[separator + 1] != 'overlay':
            continue
        for option in fields[separator + 3].split(','):
            if option.startswith('upperdir='):
                return re.sub(r'\\([0-7]{3})', lambda m: chr(int(m[1], 8)), option[9:])
    return None


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
    api = handle.client.api
    # Paths reported by a remote Engine belong to its host, not this daemon.
    # docker-py maps Unix-socket transports to this base URL (SSH differs).
    if api.base_url == 'http+docker://localhost':
        info = api.inspect_container(handle.id)
        try:
            upper = container_upper_dir(info)
            if upper:
                size = allocated_tree_bytes(upper)
                return {'disk_bytes': size, 'source': 'host_allocated_blocks'}
        except OSError:
            # Rootless/isolated Engines may expose paths we cannot read.
            # Fall back to the driver estimate, with a distinct source.
            pass
    # SDK inspect_container does not expose the Engine's size option. The list
    # endpoint does, and an exact container-ID filter limits the expensive scan.
    entries = api.containers(all=True, size=True, filters={'id': [handle.id]})
    entry = next((row for row in entries if row['Id'] == handle.id), None)
    if entry is None:
        raise RuntimeError('Container no longer exists')
    size = entry.get('SizeRw')
    if type(size) is not int or size < 0:
        raise RuntimeError('Docker storage driver did not report writable-layer size')
    return {'disk_bytes': size, 'source': 'docker_writable_layer'}


def container_image_usage(container, cache):
    """Read the immutable image actually used, caching metadata per snapshot.

    Docker's Size is an image-content estimate, not filesystem allocated blocks.
    Keep it separate from the writable layer so callers can count an image once.
    """
    handle = container.CONTAINER
    if handle is None:
        raise RuntimeError('Container has no instantiated image')
    api = handle.client.api
    image_id = api.inspect_container(handle.id).get('Image')
    if not isinstance(image_id, str) or not image_id:
        raise RuntimeError('Docker did not report the container image ID')
    key = (api.base_url, image_id)
    if key not in cache:
        image = api.inspect_image(image_id)
        size = image.get('Size')
        if type(size) is not int or size < 0:
            raise RuntimeError('Docker did not report a valid image size')
        cache[key] = dict(image_id=image_id, image_bytes=size, image_source='docker_image_size')
    return cache[key]
