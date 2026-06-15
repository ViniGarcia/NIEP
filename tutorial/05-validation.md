# Validation Checklist

This page records the baseline checks used before refactoring NIEP internals.
The goal is to keep the current Python 3 behavior reproducible while the
emulator is split into cleaner services and runtimes.

## Static Checks

Run these on the host or inside the Vagrant VM:

```bash
make test-static
```

The static check validates:

- Python syntax for `CLI/`, `TOPO-MAN/`, `VEM/`, and `tests/`.
- JSON syntax for tutorial examples, test topologies, and legacy examples.
- Markdown fence balance for the README and tutorial pages.
- Presence of the maintained tutorial artifacts.

## Integration Tests

The integration tests require the Vagrant VM because they use Mininet, libvirt,
KVM, bridges, and sudo privileges. They call the `CommandDispatcher` directly
and assert structured `ServiceResult` values instead of parsing the interactive
CLI prompt.

Run all integration tests:

```bash
make vm-test-integration
```

Run one scenario:

```bash
make vm-test-integration INTEGRATION_ARGS=mininet-isolated
make vm-test-integration INTEGRATION_ARGS=mininet-connected
make vm-test-integration INTEGRATION_ARGS=vm-host-link
make vm-test-integration INTEGRATION_ARGS=click-policy
```

The integration test plan is documented in [`../tests/PLAN.md`](../tests/PLAN.md).

## Legacy CLI Smokes

The smoke checks drive the interactive CLI non-interactively. They are kept as
compatibility checks for the legacy user interface.

Run all smoke checks:

```bash
make vm-smoke-all
```

Run one scenario:

```bash
make vm-smoke-mininet
make vm-smoke-vm
make vm-smoke-click
```

Run the full validation suite:

```bash
make vm-test-all
```

## Expected Results

`vm-smoke-mininet` loads `tutorial/examples/mininet-ping.json`, starts the
topology, enters the Mininet prompt, and runs `pingall`. Expected result:

```text
*** Results: 0% dropped
```

`vm-smoke-vm` loads `tutorial/examples/vm-basic.json`, starts the TinyCore VM,
and asks for the management address. Expected result:

```text
192.168.122.x
```

`vm-smoke-click` loads `tutorial/examples/click-forward-topology.json`, starts
the Click-on-OSv VNF with `policy-forward.click`, and runs Mininet `pingall`.
Expected result:

```text
*** Results: 33% dropped
```

This means `h1` reaches `h2`, `h2` reaches both `h1` and `h3`, and `h3` reaches
`h2`, while direct `h1 <-> h3` traffic is blocked by the Click policy.
