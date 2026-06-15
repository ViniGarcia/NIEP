#!/usr/bin/env python3
"""Validate that NIEP parser produces neutral topology specs.

This check is intended to run inside the Vagrant VM while the parser still
imports runtime modules that depend on the NIEP environment.
"""

from __future__ import annotations

import sys
from os import chdir
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "TOPO-MAN"))

from Parser import PlatformParser  # noqa: E402
from Spec import ConnectionSpec, ContainerSpec, InterfaceSpec, SFCSpec, TopologySpec, VMSpec, VNFSpec  # noqa: E402


EXAMPLES = {
    "mininet": "../tutorial/examples/mininet-ping.json",
    "vm": "../tutorial/examples/vm-basic.json",
    "vm-host-link": "../tutorial/examples/vm-host-link.json",
    "click": "../tutorial/examples/click-forward-topology.json",
    "container": "../tutorial/examples/container-host-link.json",
}


def assert_true(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def check_example(name: str, path: str) -> list[str]:
    errors: list[str] = []
    parser = PlatformParser(str(path))
    assert_true(parser.STATUS == 0, f"{name}: parser status is {parser.STATUS}", errors)
    if parser.STATUS != 0:
        detail = getattr(parser, "DETAIL", "")
        if detail:
            errors.append(f"{name}: {detail}")
        return errors

    spec = parser.SPEC
    assert_true(isinstance(spec, TopologySpec), f"{name}: parser.SPEC is not TopologySpec", errors)
    if spec is None:
        return errors

    assert_true(spec.id == parser.ID, f"{name}: spec id does not match parser id", errors)
    assert_true(len(spec.mininet_hosts) == len(parser.MNHOSTS), f"{name}: host count mismatch", errors)
    assert_true(len(spec.connections) == len(parser.CONNECTIONS), f"{name}: connection count mismatch", errors)
    assert_true(all(isinstance(link, ConnectionSpec) for link in spec.connections), f"{name}: non-spec connection found", errors)

    for host in spec.mininet_hosts:
        assert_true(
            all(isinstance(iface, InterfaceSpec) for iface in host.interfaces),
            f"{name}: host {host.id} has non-spec interface",
            errors,
        )

    assert_true(all(isinstance(vm, VMSpec) for vm in spec.vms), f"{name}: non-spec VM found", errors)
    assert_true(all(isinstance(container, ContainerSpec) for container in spec.containers), f"{name}: non-spec container found", errors)
    assert_true(all(isinstance(vnf, VNFSpec) for vnf in spec.vnfs), f"{name}: non-spec VNF found", errors)
    assert_true(all(isinstance(sfc, SFCSpec) for sfc in spec.sfcs), f"{name}: non-spec SFC found", errors)
    return errors


def main() -> int:
    chdir(ROOT / "CLI")
    failed = False
    for name, path in EXAMPLES.items():
        errors = check_example(name, path)
        if errors:
            failed = True
            print(f"[FAIL] {name}")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"[ OK ] {name}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
