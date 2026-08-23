# Docker Container Runtime

NIEP can run Docker containers as topology endpoints through the `CONTAINERS`
section. Containers are started with the Docker SDK for Python, using
`network_mode=none`, and NIEP attaches explicit veth interfaces to the
container network namespace.

The basic workflow connects one Mininet host directly to one Alpine container.
NIEP also supports containers with multiple interfaces, including routed
topologies.

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
  "IMAGE": "alpine:3.20@sha256:c64c687cbea9300178b30c95835354e34c4e4febc4badfe27102879de0483b5e",
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
  "alpine-container.json"
]
```

## Run With The Interactive CLI

Start NIEP:

```bash
cd /home/vagrant/NIEP
sudo .venv/bin/python -m niep.interfaces.cli
```

Load and start the topology:

```text
niep> define tutorial/examples/container-host-link.json
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

## Access A Container

The interactive NIEP CLI provides a container context:

```text
niep> container list
niep> container doc-alpine
container(doc-alpine)> containerexec ip -o addr show eth0
container(doc-alpine)> containershell
```

`containerexec` captures command output and returns to the NIEP prompt.
`containershell` opens an interactive TTY using `/bin/sh` by default. Exit the
shell normally to return to `container(doc-alpine)>`.

With the daemon and `niepctl`, use:

```bash
niepctl \
  container exec doc-alpine ip -o addr show eth0

niepctl \
  container shell doc-alpine
```

The shell command can be overridden, for example:

```bash
niepctl \
  container shell doc-alpine /bin/bash
```

## Multi-Interface Router

The maintained router example is:

```text
h1 (10.61.0.2/24) -- eth0 container eth1 -- h2 (10.62.0.2/24)
```

Files:

```text
tutorial/examples/container-router.json
tutorial/examples/alpine-router-container.json
```

Container interfaces are deterministic: the first `INTERFACES` entry becomes
`eth0`, the second becomes `eth1`, and so on. `SYSCTLS` are passed to Docker at
container creation time:

```json
{
  "SYSCTLS": {
    "net.ipv4.ip_forward": "1"
  },
  "INTERFACES": [
    {
      "ID": "ct-drtr0",
      "MAC": "02:00:00:00:61:01",
      "IP": "10.61.0.1/24"
    },
    {
      "ID": "ct-drtr1",
      "MAC": "02:00:00:00:62:01",
      "IP": "10.62.0.1/24"
    }
  ]
}
```

Start the topology:

```text
niep> define tutorial/examples/container-router.json
niep> topoup
niep> mininet
```

Inside Mininet, install routes through the container and test both directions:

```text
mininet> h1 ip route add 10.62.0.0/24 via 10.61.0.1
mininet> h2 ip route add 10.61.0.0/24 via 10.62.0.1
mininet> h1 ping -c2 10.62.0.2
mininet> h2 ping -c2 10.61.0.2
```

Inspect the container from another VM shell:

```bash
sudo docker exec doc-alpine-router ip -o addr show eth0
sudo docker exec doc-alpine-router ip -o addr show eth1
sudo docker exec doc-alpine-router cat /proc/sys/net/ipv4/ip_forward
```

## Current Limitations

- Containers currently use Docker only.
- Container networking is veth-based and tested for direct links and routed
  multi-interface containers.
- Docker images may be pulled on first use, so the first run needs internet
  access from the Vagrant VM.
- This is not a replacement for Click-on-OSv VNFs yet; it is the first compute
  endpoint runtime for future lightweight VNFs.
