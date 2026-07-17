# NIEP Integration Test Plan

The integration suite validates NIEP through the service layer instead of the legacy interactive CLI. Tests are executed inside the Vagrant VM because Mininet, libvirt, bridges, and Click-on-OSv require the provisioned environment and root privileges.

## Test Levels

1. Static checks
   - Python syntax.
   - JSON syntax.
   - Tutorial artifact consistency.

2. Dispatcher checks
   - Command validation.
   - Error codes for invalid commands.
   - Service-level responses without creating topology resources.
   - Validate the Typer command hierarchy and command argument parsing.

3. Parser and runtime failure checks
   - Validate field-level parser diagnostics.
   - Validate malformed JSON line and column reporting.
   - Validate Docker startup failure messages.
   - Verify failed container startup rolls back containers, veth interfaces,
     and global topology infrastructure.
   - Validate stopped/missing container command errors.

4. Topology integration checks
   - Execute topologies with `CommandDispatcher`.
   - Assert structured `ServiceResult` values.
   - Run Mininet node commands through `mininet cmd`.
   - Avoid parsing CLI prompts or banners.
   - Use self-contained topology fixtures from `tests/topologies/` and
     `tests/fixtures/`, not tutorial examples.

5. Legacy compatibility smokes
   - Keep the old CLI smoke runner to ensure the interactive CLI remains usable.

6. Heavy integration checks
   - Exercise scenarios with additional runtime dependencies or traffic
     measurements.
   - Keep them behind explicit targets so the default integration suite remains
     faster and less sensitive to throughput variance.

## Current Integration Scenarios

1. Isolated Mininet hosts
   - Load a topology with two unconnected Mininet hosts.
   - Verify both hosts exist and have the configured addresses.
   - Verify host-to-host communication fails.

2. Connected Mininet hosts
   - Load `tests/topologies/mininet-connected-hosts.json`.
   - Verify `mininet pingall` has 0% packet loss.
   - Verify direct host command connectivity from `h1` to `h2`.

3. TinyCore VM connected to a Mininet host
   - Load `tests/topologies/vm-host-link.json`.
   - Retrieve the VM management address through the service.
   - Configure the VM data interface over SSH.
   - Verify the Mininet host reaches the VM data interface.

4. Click-on-OSv policy VNF
   - Load `tests/topologies/click-policy-vnf.json`.
   - Upload and start `tests/fixtures/click/policy-forward.click`.
   - Verify the policy behavior:
     - `h1` reaches `h2`.
     - `h2` reaches `h3`.
     - `h1` cannot reach `h3`.

5. Docker container connected to a Mininet host
   - Load `tests/topologies/container-host-link.json`.
   - Start an Alpine container through the Docker SDK.
   - Attach a veth interface to the container network namespace.
   - Verify `h1` reaches the container.
   - Verify the container reaches `h1` through `container exec`.

6. Multi-interface Docker router
   - Load `tests/topologies/container-router.json`.
   - Start one Alpine container with two veth interfaces in different subnets.
   - Apply `net.ipv4.ip_forward=1` through declarative container sysctls.
   - Verify deterministic `eth0` and `eth1` addresses and MACs.
   - Install routes on two Mininet hosts and verify bidirectional forwarding.
   - Verify the container and both host-side veth interfaces are removed after
     `topodown`.

7. Container command access
   - Validate non-interactive `container exec` through the service socket.
   - Validate an interactive Docker exec stream through `container shell`.
   - Verify shell output traverses the Unix socket before the session closes.

8. niepctl completion and UX
   - Validate the Typer command hierarchy and contextual help.
   - Validate non-interactive output and container exit-code propagation.
   - Simulate Bash completion against a running daemon.
   - Verify active container and VM IDs are returned as completion candidates.

## Heavy Integration Scenarios

1. iperf3 containers through Click policing
   - Build `niep/iperf3-test:local` from `tests/fixtures/containers/iperf3`.
   - Load `tests/topologies/iperf-click-shaper.json`.
   - Start a Click-on-OSv VNF with `tests/fixtures/click/udp-shaper.click`.
   - Verify container addressing and basic reachability.
   - Verify TCP traffic passes through the VNF.
   - Verify UDP offered at 20 Mbit/s is policed by observing a lower receiver
     bitrate and packet loss.

## Running

From the host:

```bash
make vm-test-integration
```

To run parser and Docker failure checks:

```bash
make vm-test-errors
```

To run only one scenario:

```bash
make vm-test-integration INTEGRATION_ARGS="mininet-connected"
```

To run the heavy iperf3 policing scenario:

```bash
make vm-test-iperf-shaper
```

The full validation target is:

```bash
make vm-test-all
```
