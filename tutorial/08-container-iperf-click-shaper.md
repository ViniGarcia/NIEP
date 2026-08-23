# Container iperf3 With Click Policing

This example runs two Alpine containers with a Click-on-OSv VNF between them:

```text
doc-iperf-client -- s1 -- click-shaper -- s2 -- doc-iperf-server
```

The Click function forwards L2 traffic and applies a simple UDP packet-rate
policer from the client side to the server side. It uses `RatedSplitter(200)`,
so UDP above roughly 200 packets/s is discarded. This is packet-rate policing,
not a precise bandwidth shaper.

## Files

```text
tutorial/examples/container-iperf-click-shaper.json
tutorial/examples/iperf-client-container.json
tutorial/examples/iperf-server-container.json
tutorial/examples/click-shaper-vnf.json
tutorial/examples/click-shaper-vm.json
tutorial/examples/click/udp-shaper.click
tutorial/examples/containers/iperf3/Dockerfile
tutorial/examples/containers/iperf3/docker-compose.yml
```

The containers use the local image `niep/iperf3:local`, built from a Dockerfile
included with the tutorial. NIEP only consumes the image; the build step remains
explicit and outside the emulator lifecycle. The server container starts
`iperf3 -s` as its main process, while the client container stays idle so you can
run client-side commands manually with `docker exec`.

## Build The Local iperf3 Image

Build the image inside the Vagrant VM:

```bash
make vm-build-iperf3-image
```

Equivalent direct command inside the VM:

```bash
cd /home/vagrant/NIEP/tutorial/examples/containers/iperf3
sudo docker compose build
```

The resulting image is:

```text
niep/iperf3:local
```

## Start The Topology

From the canonical NIEP CLI:

```bash
cd /home/vagrant/NIEP
sudo .venv/bin/python -m niep.interfaces.cli
```

```text
niep> define tutorial/examples/container-iperf-click-shaper.json
niep> topoup
niep> vnf click-shaper
vnf(click-shaper)> vnfaction POST_FUNCTION tutorial/examples/click/udp-shaper.click
vnf(click-shaper)> vnfaction POST_START
vnf(click-shaper)> exit
```

## Inspect The Containers

If the topology is running through the interactive CLI, use Docker directly
inside the VM:

```bash
make vm-ssh
cd /home/vagrant/NIEP
sudo docker exec doc-iperf-client ip -o addr show eth0
sudo docker exec doc-iperf-server ip -o addr show eth0
```

## Service API Alternative

You can also run the same topology through the NIEP daemon. In one terminal:

```bash
make vm-daemon
```

In another terminal:

```bash
make vm-ctl NIEPCTL_ARGS="--json define tutorial/examples/container-iperf-click-shaper.json"
make vm-ctl NIEPCTL_ARGS="--json topoup"
make vm-ctl NIEPCTL_ARGS="--json vnf action click-shaper POST_FUNCTION tutorial/examples/click/udp-shaper.click"
make vm-ctl NIEPCTL_ARGS="--json vnf action click-shaper POST_START"
make vm-ctl NIEPCTL_ARGS="--json container exec doc-iperf-client iperf3 -u -b 20M -c 10.70.0.2 -t 10"
make vm-ctl NIEPCTL_ARGS="--json topodown"
```

## Run iperf3

TCP sanity check:

```bash
sudo docker exec doc-iperf-client iperf3 -c 10.70.0.2 -t 5
```

UDP test with the Click policer:

```bash
sudo docker exec doc-iperf-client iperf3 -u -b 20M -c 10.70.0.2 -t 10
```

## Expected Results

ARP and non-UDP traffic should pass through the VNF. A TCP test is therefore
expected to report a high bitrate, usually in the Gbit/s range inside the VM:

```text
sender/receiver: several Gbits/sec
```

The default UDP `iperf3` rate is about 1 Mbit/s. That is below the configured
`RatedSplitter(200)` packet rate, so this test may show little or no loss:

```bash
sudo docker exec doc-iperf-client iperf3 -u -c 10.70.0.2 -t 10
```

Expected shape:

```text
sender/receiver: about 1 Mbit/sec
lost datagrams: 0% or close to 0%
```

To make the policer visible, offer more UDP traffic:

```bash
sudo docker exec doc-iperf-client iperf3 -u -b 20M -c 10.70.0.2 -t 10
```

Expected shape:

```text
sender:   about 20 Mbits/sec
receiver: clearly lower than the sender rate
loss:     high packet loss
```

For example, with the current `RatedSplitter(200)` configuration, one observed
run sent `20.0 Mbits/sec` and received about `2.3 Mbits/sec`, with roughly
`88%` packet loss.

This Click function is a packet-rate policer, not a queue-based bandwidth
shaper. It discards packets above the configured packet rate, so `iperf3`
reports the effect as packet loss. The resulting Mbit/s value depends on packet
size.

If you stop the VNF function, traffic between the containers should stop because
the VNF is the only path between both sides:

```text
vnf(click-shaper)> vnfaction POST_STOP
```

Restart forwarding with:

```text
vnf(click-shaper)> vnfaction POST_START
```

## Stop The Topology

```text
niep> topodown
```

If something is left behind:

```bash
make vm-clean
```
