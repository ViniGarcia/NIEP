# NIEP Tutorial

This tutorial is organized as a short sequence of runnable examples, from the simplest Mininet topology to a Click-on-OSv VNF with policy enforcement.

Run the canonical interactive interface from the repository root:

```bash
cd /home/vagrant/NIEP
sudo .venv/bin/python -m niep.interfaces.cli
```

## Sequence

1. [Setup and workflow](00-setup.md)
2. [Mininet ping between two hosts](01-mininet-ping.md)
3. [TinyCore VM management test](02-vm-basic.md)
4. [TinyCore VM connected to a Mininet host](03-vm-host-link.md)
5. [Click-on-OSv VNF with forwarding policy](04-click-vnf-policy.md)
6. [Validation checklist](05-validation.md)
7. [NIEP service socket and niepctl](06-service-api.md)
8. [Docker container runtime](07-container-runtime.md)
9. [Container iperf3 with Click policing](08-container-iperf-click-shaper.md)
10. [Troubleshooting](99-troubleshooting.md)

The old `EXAMPLES/` directory is useful to understand the original project, but some examples may be stale or inconsistent. The examples in this tutorial are maintained independently under `tutorial/examples/`.
