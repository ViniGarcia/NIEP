# NIEP Tutorial

This tutorial is organized as a short sequence of runnable examples, from the simplest Mininet topology to a Click-on-OSv VNF with policy enforcement.

Run NIEP from the `CLI/` directory. All example paths below assume the prompt is started with:

```bash
cd /home/vagrant/NIEP/CLI
sudo python3 CLI.py
```

## Sequence

1. [Setup and workflow](00-setup.md)
2. [Mininet ping between two hosts](01-mininet-ping.md)
3. [TinyCore VM management test](02-vm-basic.md)
4. [TinyCore VM connected to a Mininet host](03-vm-host-link.md)
5. [Click-on-OSv VNF with forwarding policy](04-click-vnf-policy.md)
6. [Validation checklist](05-validation.md)
7. [Troubleshooting](99-troubleshooting.md)

The old `EXAMPLES/` directory is useful to understand the original project, but some examples may be stale or inconsistent. The examples in this tutorial are maintained independently under `tutorial/examples/`.
