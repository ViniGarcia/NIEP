#!/usr/bin/env python3
"""Check for resources left by the Alpine HTTP example topology."""

import subprocess
import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
DOMAIN = "bench-vm01"
NETWORK = "vnNIEP"
LINKS = ("virbrNIEP", "br-bench0", "vbrNIEP")


def command(*args):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.DEVNULL)


def report(label, leftover):
    print(f"{'LEFTOVER' if leftover else 'CLEAN'}: {label}")
    return leftover


def main():
    failed = False

    domains = command("virsh", "-c", "qemu:///system", "list", "--all", "--name")
    if domains.returncode:
        print("ERROR: could not query system libvirt domains; run with sudo")
        return 2
    failed |= report(f"libvirt domain {DOMAIN}", DOMAIN in domains.stdout.splitlines())

    networks = command("virsh", "-c", "qemu:///system", "net-list", "--all", "--name")
    if networks.returncode:
        print("ERROR: could not query system libvirt networks; run with sudo")
        return 2
    failed |= report(f"libvirt network {NETWORK}", NETWORK in networks.stdout.splitlines())

    for link in LINKS:
        result = command("ip", "link", "show", "dev", link)
        failed |= report(f"network interface {link}", result.returncode == 0)

    processes = command("ps", "-eo", "pid=,comm=,args=")
    if processes.returncode:
        print("ERROR: could not inspect processes")
        return 2
    leftovers = []
    for line in processes.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) < 2:
            continue
        pid, name = fields[:2]
        if pid == str(os.getpid()):
            continue
        if name in {"mnexec", "mininet"} or (len(fields) == 3 and "/mininet/" in fields[2]):
            leftovers.append(line.strip())
    failed |= report("Mininet processes" + (f": {'; '.join(leftovers)}" if leftovers else ""), bool(leftovers))

    instance_dir = ROOT / "VEM" / "IMAGES" / DOMAIN
    failed |= report(f"instance files at {instance_dir}", instance_dir.exists())
    print("Summary: cleanup incomplete" if failed else "Summary: no Alpine topology resources found")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
