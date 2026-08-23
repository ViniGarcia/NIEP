# Changelog

All notable NIEP changes are recorded here. The `1.2.0a1` entry is a
pre-release: compatibility paths are still available, but new deployments
should use the canonical package and command interfaces.

## [1.2.0a1] - 2026-08-23

### Breaking changes

- None planned for this pre-release. The old `TOPO-MAN` and `VEM` imports,
  legacy launchers and compatibility fields remain available through the
  `1.2.x` line.

### Added

- Typed topology specifications and deterministic connection planning.
- Transactional topology lifecycle with resumable cleanup state.
- A shared application command port for `niepctl`, `niepd` and the interactive
  CLI, using `niep.command` protocol version 1.
- Linux peer-credential authorization, bounded Unix-socket framing and bounded
  interactive sessions.
- Reproducible Python, Vagrant and container-image environment checks.

### Fixed

- Teardown and startup rollback now preserve structured diagnostics and can be
  retried after partial failures.
- Package imports no longer require changing the process `sys.path`.
- Public socket responses no longer expose internal runtime details or raw
  interactive streams.

### Compatibility and deprecations

- The 19 historical `TOPO-MAN/*.py` and `VEM/*.py` module paths remain thin
  shims and emit `DeprecationWarning` with their canonical replacement.
- `CLI/CLI.py`, `CLI/Launcher.py`, `CLI/HTTP.py`, `tools/niepctl.py`,
  `tools/niepd.py` and the `tools/niepctl` shell wrapper remain compatibility
  launchers for one cycle and warn on use.
- The canonical interfaces are the installed `niepctl`/`niepd` entry points,
  `python -m niep.interfaces.cli`, and typed application ports.
- Removal is not earlier than NIEP `1.3.0`, subject to the compatibility
  policy in [`docs/adr/0001-compatibility-policy.md`](docs/adr/0001-compatibility-policy.md).

### Third-party components

- The vendored POX tree remains a deployment asset and is excluded from the
  NIEP wheel. Its known provenance and current content baseline are recorded
  in [`docs/pox-provenance.md`](docs/pox-provenance.md).
