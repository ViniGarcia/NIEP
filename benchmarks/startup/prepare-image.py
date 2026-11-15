#!/usr/bin/env python3
"""Inspect or install procedural startup addressing on an offline Alpine QCOW2 copy.

No mounts, root permissions or guest credentials are needed. The source is never
modified; an update produces a new disk to install while the daemon is idle.
"""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile


from niep.domain.startup_addressing import positive_count, validate_count

NETWORK = Path(__file__).resolve().parents[1] / 'images/alpine-http/guest/network'


def command(*args):
    return subprocess.run(args, capture_output=True, text=True, check=True).stdout


def copy_bytes(source, target, size):
    while size:
        block = source.read(min(size, 4 * 1024 * 1024))
        if not block:
            raise RuntimeError('Truncated disk partition')
        target.write(block)
        size -= len(block)


def process(source, output=None, count=16):
    validate_count(count)
    with tempfile.TemporaryDirectory(prefix='niep-startup-image-') as work:
        work = Path(work)
        raw, partition = work / 'disk.raw', work / 'root.ext4'
        command('qemu-img', 'convert', '-O', 'raw', str(source), str(raw))
        table = json.loads(command('sfdisk', '--json', str(raw)))['partitiontable']
        parts = table['partitions']
        if len(parts) != 1 or parts[0]['type'] != '83':
            raise RuntimeError('Expected the Alpine builder single Linux partition layout')
        offset = parts[0]['start'] * table['sectorsize']
        length = parts[0]['size'] * table['sectorsize']
        with raw.open('rb') as disk, partition.open('wb') as root:
            disk.seek(offset)
            copy_bytes(disk, root, length)
        expected = NETWORK.read_text()
        current = command('debugfs', '-R', 'cat /etc/init.d/niep-network', str(partition))
        if output is None:
            if current != expected:
                raise RuntimeError('VM base lacks current procedural startup addressing. '
                                   'Run prepare-image.py SOURCE --output NEW_IMAGE and install the copy; '
                                   'see benchmarks/startup/README.md.')
            print(f'PASS: VM base supports procedural addressing for {count} instances')
            return
        if output.exists():
            raise RuntimeError(f'Refusing to overwrite {output}')
        script = work / 'niep-network'
        script.write_text(expected)
        command('debugfs', '-w', '-R', 'rm /etc/init.d/niep-network', str(partition))
        command('debugfs', '-w', '-R', f'write {script} /etc/init.d/niep-network', str(partition))
        command('debugfs', '-w', '-R', 'set_inode_field /etc/init.d/niep-network mode 0100755', str(partition))
        updated = command('debugfs', '-R', 'cat /etc/init.d/niep-network', str(partition))
        metadata = command('debugfs', '-R', 'stat /etc/init.d/niep-network', str(partition))
        if updated != expected or not re.search(r'Mode:\s+0755', metadata):
            raise RuntimeError('Could not verify executable guest network script')
        command('e2fsck', '-fn', str(partition))
        with partition.open('rb') as root, raw.open('r+b') as disk:
            disk.seek(offset)
            copy_bytes(root, disk, length)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Convert to a temporary name first; a failed conversion leaves no usable output.
        staged = work / 'updated.qcow2'
        command('qemu-img', 'convert', '-O', 'qcow2', str(raw), str(staged))
        command('qemu-img', 'check', str(staged))
        with output.open('xb') as destination, staged.open('rb') as disk:
            shutil.copyfileobj(disk, destination)
        print(f'Prepared {output}; source retained: {source}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', type=Path, help='Create a corrected copy; omit to check only')
    parser.add_argument('--count', type=positive_count, default=16)
    args = parser.parse_args()
    try:
        process(args.source.resolve(), args.output.resolve() if args.output else None, args.count)
    except (RuntimeError, ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
