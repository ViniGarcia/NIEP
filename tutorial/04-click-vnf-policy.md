# 04 - Click-on-OSv VNF With Forwarding Policy

Files used:

- `tutorial/examples/click-forward-vm.json`: VM definition using the `click-on-osv` disk.
- `tutorial/examples/click-forward-vnf.json`: VNF definition that wraps the VM.
- `tutorial/examples/click-forward-topology.json`: topology with three Mininet hosts and the VNF.
- `tutorial/examples/click/policy-forward.click`: Click function with a forwarding policy.
- `tutorial/examples/click/policy-forward-start.ns`: script that loads and starts the policy function.
- `tutorial/examples/click/policy-forward-reload.ns`: script that stops, replaces, and restarts the running function.

Topology:

```text
h1 10.30.0.1/24 -- click-forward -- s1 -- h2 10.30.0.2/24
                                           \-- h3 10.30.0.3/24
```

The policy permits `h1 <-> h2` and `h2 <-> h3`, but blocks IP traffic between `h1` and `h3`.

Relevant Click rules:

```click
block_h1_to_h3 :: IPFilter(
    deny src 10.30.0.1 && dst 10.30.0.3,
    allow all
);

block_h3_to_h1 :: IPFilter(
    deny src 10.30.0.3 && dst 10.30.0.1,
    allow all
);
```

Before running this example, make sure the real Git LFS images are present:

```bash
make check-images
make vm-sync
make vm-reset-tutorial-vm
make vm-libvirt-perms
make vm-cli
```

At the `niep>` prompt:

```text
define ../tutorial/examples/click-forward-topology.json
topoup
vnf list
vnf click-forward
vnfmanagement
```

Load and start the policy function:

```text
vnfaction POST_FUNCTION ../tutorial/examples/click/policy-forward.click
vnfaction GET_FUNCTION
vnfaction POST_START
vnfaction GET_RUNNING
```

Or use the script:

```text
vnfscript ../tutorial/examples/click/policy-forward-start.ns
```

If a Click function is already running, stop it before replacing the file. `POST_FUNCTION` writes a new `func.click`, but the running Click process keeps using the old function until restarted:

```text
vnfaction POST_STOP
vnfaction POST_FUNCTION ../tutorial/examples/click/policy-forward.click
vnfaction POST_START
vnfaction GET_RUNNING
```

Or use:

```text
vnfscript ../tutorial/examples/click/policy-forward-reload.ns
```

Return to the main prompt and open Mininet:

```text
exit
mininet
```

At the `mininet>` prompt:

```text
h3 ping -c 3 10.30.0.2  # should work
h3 ping -c 3 10.30.0.1  # should fail
h1 ping -c 3 10.30.0.3  # should fail
h2 ping -c 3 10.30.0.1  # should work
pingall                  # expected: h1<->h3 fails, the other pairs work
exit
```

Clean up:

```text
topodown
topodestroy
```

`tutorial/examples/click/forward.click` is also available as an unrestricted pass-through function. If you load it, all hosts should be able to ping each other.
