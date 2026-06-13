# 01 - Mininet Ping Between Two Hosts

File used: `tutorial/examples/mininet-ping.json`.

Topology:

```text
h1 10.10.0.1/24 -- s1 -- h2 10.10.0.2/24
```

At the `niep>` prompt:

```text
define ../tutorial/examples/mininet-ping.json
topoup
mininet
```

At the `mininet>` prompt:

```text
nodes
h1 ip addr show
h2 ip addr show
h1 ping -c 4 10.10.0.2
```

Expected result:

```text
4 packets transmitted, 4 received, 0% packet loss
```

Clean up:

```text
exit
topodown
```
