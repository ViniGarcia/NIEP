# 03 - TinyCore VM Connected to a Mininet Host

Files used:

- `tutorial/examples/tinycore-vm-data.json`: VM definition with one data interface.
- `tutorial/examples/vm-host-link.json`: topology connecting the VM to a Mininet host.

Topology:

```text
h1 10.20.0.1/24 -- br-doc0 -- doc-tinycore-link eth1 10.20.0.2/24
```

NIEP creates the virtual wiring, but TinyCore still needs an IP address on the data interface.

At the `niep>` prompt:

```text
define ../tutorial/examples/vm-host-link.json
topoup
vm doc-tinycore-link
vmmanagement
vmssh tc NIEPvm00
```

Inside TinyCore, find the interface with MAC `52:54:02:00:10:01`. It is usually `eth1`:

```sh
ifconfig -a
sudo ifconfig eth1 10.20.0.2 netmask 255.255.255.0 up
ping -c 3 10.20.0.1
exit
```

Back in the NIEP VM prompt:

```text
exit
mininet
```

At the `mininet>` prompt:

```text
h1 ping -c 3 10.20.0.2
exit
```

Clean up:

```text
topodown
topodestroy
```

This pattern is the basis for more useful VM scenarios: start a service inside TinyCore, add a second data interface, or configure forwarding/bridging inside the VM.
