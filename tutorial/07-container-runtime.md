# Docker Container Runtime

NIEP can run Docker containers as topology endpoints through the `CONTAINERS`
section. Containers are started with the Docker SDK for Python, using
`network_mode=none`, and NIEP attaches explicit veth interfaces to the
container network namespace.

The first supported container workflow is intentionally small: one Mininet host
connected directly to one Alpine container.

## Topology Files

The tutorial example uses:

```text
tutorial/examples/container-host-link.json
tutorial/examples/alpine-container.json
```

The container descriptor is:

```json
{
  "ID": "doc-alpine",
  "IMAGE": "alpine:3.20",
  "COMMAND": ["sleep", "infinity"],
  "PRIVILEGED": true,
  "INTERFACES": [
    {
      "ID": "ct-doc0",
      "MAC": "02:00:00:00:60:02",
      "IP": "10.60.0.2/24"
    }
  ]
}
```

The topology references it through `CONTAINERS`:

```json
"CONTAINERS": [
  "../tutorial/examples/alpine-container.json"
]
```

## Run With The Interactive CLI

Start NIEP:

```bash
cd /home/vagrant/NIEP/CLI
sudo python3 CLI.py
```

Load and start the topology:

```text
niep> define ../tutorial/examples/container-host-link.json
niep> topoup
```

Enter Mininet and ping the container:

```text
niep> mininet
mininet> h1 ping -c1 10.60.0.2
mininet> exit
```

Then stop the topology:

```text
niep> topodown
```

## Run With The Service API

Start the daemon:

```bash
make vm-daemon
```

In another terminal:

```bash
make vm-ctl NIEPCTL_ARGS="--json define tutorial/examples/container-host-link.json"
make vm-ctl NIEPCTL_ARGS="--json topoup"
make vm-ctl NIEPCTL_ARGS="--json container list"
make vm-ctl NIEPCTL_ARGS="--json container exec doc-alpine ip -o addr show eth0"
make vm-ctl NIEPCTL_ARGS="--json mininet cmd h1 ping -c1 -W2 10.60.0.2"
make vm-ctl NIEPCTL_ARGS="--json topodown"
```

## Current Limitations

- Containers currently use Docker only.
- Container networking is veth-based and tested for direct host-container links.
- Docker images may be pulled on first use, so the first run needs internet
  access from the Vagrant VM.
- This is not a replacement for Click-on-OSv VNFs yet; it is the first compute
  endpoint runtime for future lightweight VNFs.
