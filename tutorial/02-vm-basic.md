# 02 - TinyCore VM Management Test

Files used:

- `tutorial/examples/tinycore-vm.json`: VM definition.
- `tutorial/examples/vm-basic.json`: topology that instantiates the VM.

This example starts only the VM. It validates libvirt/KVM, the TinyCore base image, the NIEP VM lifecycle, and SSH over the management network.

At the `niep>` prompt:

```text
define ../tutorial/examples/vm-basic.json
topoup
vm list
vm doc-tinycore
vmmanagement
```

`vmmanagement` should print a DHCP address from `vnNIEP`, for example:

```text
192.168.100.128
```

If it prints `ARP PROBLEMS`, wait a few seconds and run `vmmanagement` again. You can also check leases from the host:

```bash
vagrant ssh -- -t "sudo virsh net-dhcp-leases vnNIEP"
```

Open SSH through NIEP:

```text
vmssh tc NIEPvm00
```

Inside TinyCore:

```sh
hostname
ifconfig -a
ping -c 3 192.168.100.1
exit
```

Back in `vm(doc-tinycore)>`, return to the main prompt and clean up:

```text
exit
topodown
topodestroy
```
