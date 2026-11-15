#!/usr/bin/env python3
"""Inspect or update the startup MAC map on an offline Alpine QCOW2 copy.

No mounts, root permissions or guest credentials are needed. The source is never
modified; an update produces a new disk to install while the daemon is idle.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import tempfile


MAP = Path(__file__).with_name('network-map')


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
        expected = MAP.read_text().splitlines()[:count]
        current = command('debugfs', '-R', 'cat /etc/niep-network.conf', str(partition))
        mappings = {tuple(line.lower().split()) for line in current.splitlines()
                    if line.strip() and not line.lstrip().startswith('#')}
        missing = [line for line in expected if tuple(line.lower().split()) not in mappings]
        if output is None:
            if missing:
                raise RuntimeError(f'VM base lacks {len(missing)} required MAC mappings. '
                                   'Run prepare-image.py to create and install a corrected copy; '
                                   'see benchmarks/startup/README.md. Missing: ' + ', '.join(missing))
            print(f'PASS: VM base contains all {count} startup MAC mappings')
            return
        if output.exists():
            raise RuntimeError(f'Refusing to overwrite {output}')
        # Merge required mappings while retaining unrelated caller configuration.
        wanted = {line.split()[0].lower() for line in MAP.read_text().splitlines()}
        retained = [line for line in current.splitlines()
                    if not line.split() or line.split()[0].lower() not in wanted]
        merged = work / 'network-map'
        merged.write_text('\n'.join(retained) + '\n' + MAP.read_text())
        command('debugfs', '-w', '-R', 'rm /etc/niep-network.conf', str(partition))
        command('debugfs', '-w', '-R', f'write {merged} /etc/niep-network.conf', str(partition))
        updated = command('debugfs', '-R', 'cat /etc/niep-network.conf', str(partition))
        if updated != merged.read_text():
            raise RuntimeError('Could not verify updated guest map')
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
    parser.add_argument('--count', type=int, default=16, choices=(1, 2, 4, 8, 16))
    args = parser.parse_args()
    try:
        process(args.source.resolve(), args.output.resolve() if args.output else None, args.count)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
