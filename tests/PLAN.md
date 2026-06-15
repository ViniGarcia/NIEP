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

3. Topology integration checks
   - Execute topologies with `CommandDispatcher`.
   - Assert structured `ServiceResult` values.
   - Run Mininet node commands through `mininet cmd`.
   - Avoid parsing CLI prompts or banners.
   - Use self-contained topology fixtures from `tests/topologies/` and
     `tests/fixtures/`, not tutorial examples.

4. Legacy compatibility smokes
   - Keep the old CLI smoke runner to ensure the interactive CLI remains usable.

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

## Running

From the host:

```bash
make vm-test-integration
```

To run only one scenario:

```bash
make vm-test-integration INTEGRATION_ARGS="mininet-connected"
```

The full validation target is:

```bash
make vm-test-all
```
