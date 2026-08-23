# ADR 0002: Keep POX vendored as a deployment asset

- Status: accepted for `1.2.0a1`
- Date: 2026-08-23

## Context

NIEP runs controller code beside Mininet in a provisioned Ubuntu VM. The
project's wheel intentionally contains only the maintained `niep` package;
large VM assets and the controller tree are supplied by a checkout. The
repository's POX history includes a Python 3 update, but the exact upstream ref
for that update was not recorded.

## Decision

Keep `OFCONTROLLERS/pox/` vendored and separate from the NIEP package. Do not
make it a runtime pip dependency, submodule or mutable download. Record the
known upstream project, named series, NIEP import commit and deterministic
current tree hash in [`docs/pox-provenance.md`](../pox-provenance.md).

An upcoming POX update must add its exact upstream commit/archive hash and a
patch manifest. The existing `LICENSE` and `NOTICE` remain mandatory release
files. Maintained-code checks must continue to exclude the tree explicitly.

## Consequences

Offline VM setup and release archives remain deterministic, at the cost of
manual upstream update work. Provenance is currently limited by the missing
historical upstream ref; this is documented rather than guessed.
