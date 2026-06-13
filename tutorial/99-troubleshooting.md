# 99 - Troubleshooting and Validation

## Git LFS Images

The files under `VEM/IMAGES/*.qcow2` are managed by Git LFS. If they were not fetched, they are small text pointer files instead of real qcow2 disks. QEMU then fails with:

```text
Image is not in qcow2 format
```

Check and fetch images from the host repository root:

```bash
make check-images
sudo apt-get install -y git-lfs
make lfs-pull
make check-images
make vm-sync
make vm-check-images
```

The expected `tinycore12.qcow2` size is about 107 MB.

## libvirt Image Permissions

If `topoup` fails with:

```text
Cannot access storage file ... Permission denied
```

run:

```bash
make vm-libvirt-perms
make vm-reset-tutorial-vm
make vm-cli
```

## Cleanup After Failed Runs

Outside the NIEP CLI:

```bash
make vm-clean
make vm-reset-tutorial-vm
```

Inside the VM, equivalent manual cleanup commands are:

```bash
sudo mn -c
sudo virsh net-destroy vnNIEP
sudo ip link set vbrNIEP down
sudo brctl delbr vbrNIEP
```

Ignore messages saying a resource does not exist; they only mean that part was already clean.

## JSON-Only Validation

Validate syntax:

```bash
jq empty tutorial/examples/*.json
```

Validate that NIEP can parse the tutorial topologies without starting them:

```bash
cd /home/vagrant/NIEP/CLI
python3 - <<'PY'
import sys
sys.path.insert(0, '../TOPO-MAN')
from Parser import PlatformParser
for definition in [
    '../tutorial/examples/mininet-ping.json',
    '../tutorial/examples/vm-basic.json',
    '../tutorial/examples/vm-host-link.json',
    '../tutorial/examples/click-forward-topology.json',
]:
    p = PlatformParser(definition)
    print(definition, p.STATUS, getattr(p, 'DETAIL', ''))
PY
```

Expected status is `0` for all files.

## Useful NIEP CLI Commands

```text
help
vm list
vnf list
sfc list
mininet
topodown
topodestroy
```
