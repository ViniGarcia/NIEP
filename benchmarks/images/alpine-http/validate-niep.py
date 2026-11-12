#!/usr/bin/env python3
"""Exercise NIEP's real VM/image-store adapters without requiring Mininet."""
import argparse
import http.client
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

from niep.runtime.libvirt import LibvirtRuntime
from niep.runtime.vm import VM
from niep.runtime.vm_image_store import VMImageStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("key", type=Path)
    args = parser.parse_args()
    image, key = args.image.resolve(), args.key.resolve()
    template = Path(__file__).resolve().parents[3] / "VEM/IMAGES/alpine-http.xml"
    runtime = LibvirtRuntime()
    connection = runtime.get_connection()
    network = connection.networkLookupByName("default")
    if not network.isActive():
        parser.error("libvirt's default network must be active")
    identifier = "niep-alpine-check-" + uuid.uuid4().hex[:10]
    mac = "52:54:" + ":".join(f"{b:02x}" for b in uuid.uuid4().bytes[:4])
    # A traversable location allows system libvirt to access these private copies.
    work = tempfile.mkdtemp(prefix="niep-alpine-", dir="/var/tmp")
    root = Path(work)
    try:
        root.chmod(0o755)
        images = root / "IMAGES"
        images.mkdir()
        shutil.copyfile(image, images / "alpine-http.qcow2")
        shutil.copyfile(template, images / "alpine-http.xml")
        descriptor = root / "vm.json"
        descriptor.write_text(json.dumps({
            "ID": identifier, "MEMORY": 256, "VCPU": 1, "DISK": "alpine-http",
            "MANAGEMENT_MAC": mac, "INTERFACES": [],
        }))
        vm = VM(str(descriptor), None, None, runtime=runtime, image_store=VMImageStore(work))
        try:
            assert vm.VM_STATUS == 0, vm.VM_STATUS
            assert vm.createVM() == 0
            assert vm.upVM() == 0
            address = None
            for _ in range(120):
                leases = network.DHCPLeases()
                address = next((lease["ipaddr"] for lease in leases
                                if lease.get("mac") == mac), None)
                if address:
                    client = http.client.HTTPConnection(address, 8080, timeout=1)
                    try:
                        client.request("GET", "/health")
                        response = client.getresponse()
                        if response.status == 200 and response.read() == b"ok":
                            break
                    except OSError:
                        pass
                    finally:
                        client.close()
                time.sleep(1)
            else:
                raise RuntimeError("NIEP VM did not reach HTTP readiness within 120 attempts")
            ssh = ["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "ConnectTimeout=2",
                   "-o", "StrictHostKeyChecking=accept-new", "-o",
                   f"UserKnownHostsFile={root / 'known_hosts'}", f"root@{address}"]
            for _ in range(30):
                if subprocess.run([*ssh, "true"], stderr=subprocess.DEVNULL).returncode == 0:
                    break
                time.sleep(1)
            else:
                raise RuntimeError("SSH did not become available")
            subprocess.run([*ssh, "poweroff"], check=True)
            for _ in range(30):
                if not runtime.is_running(identifier):
                    break
                time.sleep(1)
            else:
                raise RuntimeError("Guest did not shut down cleanly")
            print("PASS: NIEP createVM/applyVM/upVM, libvirt DHCP, HTTP 200 ok, SSH, clean poweroff")
        finally:
            assert vm.cleanupVM() == 0, vm.CLEANUP_ERRORS
            assert vm.destroyVM() == 0
        assert not runtime.exists(identifier)
        assert not (images / identifier).exists()
        assert image.is_file()
        print("PASS: NIEP removed the temporary domain and instance; source base retained")
    finally:
        if runtime.exists(identifier):
            print(f"Domain {identifier} still exists; retained disks at {root}", file=sys.stderr)
        else:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
