# NIEP release checklist

This checklist is for the `v1.2.0a1` pre-release and future compatible
releases. A release must be reproducible from the commit that receives the
tag. The local files `REFATORACOES.md` and `plano-refatoracao/` are planning
artifacts and must never be staged as release content.

## Before tagging

- [ ] T01–T12 acceptance criteria are reviewed.
- [ ] `pyproject.toml`, `niep.__version__`, README and changelog agree on the
      version.
- [ ] All 19 module shims, `CLI/HTTP.py`, four Python launchers and the
      `tools/niepctl` shell wrapper emit a destination and removal version.
- [ ] The compatibility inventory and migration guide are current.
- [ ] POX provenance and current content baseline are present.
- [ ] `make test` passes on the host.
- [ ] `make ci-check` and `git diff --check` pass.
- [ ] No generated build files, virtualenvs, credentials or local planning
      files are staged.

`MANIFEST.in` defines the artifact boundary: an sdist carries the changelog,
documentation/ADRs, tutorial, legacy shim/launcher source and the vendored POX
tree with `LICENSE` and `NOTICE`; large VM disk images remain provisioning
inputs. The wheel contains only `niep*` packages and intentionally excludes
POX, VM images and CLI history. The two artifacts are checked separately.

## Clean archive proof

Run from the candidate commit, using a temporary directory outside the
checkout:

```bash
release_tmp=$(mktemp -d)
git archive --format=tar --prefix=niep-1.2.0a1/ HEAD \
  | tar -x -C "$release_tmp"
cd "$release_tmp/niep-1.2.0a1"
python3 -m venv "$release_tmp/venv"
# Build tools are pinned by constraints and pyproject.toml. Installing them
# explicitly makes --no-build-isolation reproducible and avoids relying on
# whatever a freshly-created venv happens to contain.
"$release_tmp/venv/bin/python" -m pip install \
  --constraint constraints/py3-linux.txt \
  pip==24.3.1 setuptools==75.6.0 wheel==0.45.1
"$release_tmp/venv/bin/python" -m pip wheel . --no-deps --no-build-isolation \
  --wheel-dir "$release_tmp/wheel"
# Functional install: resolve the wheel's declared runtime dependencies under
# the same pinned constraints. The unquoted glob is intentional so the shell
# expands the single candidate wheel before pip receives it.
"$release_tmp/venv/bin/python" -m pip install \
  --constraint "$release_tmp/niep-1.2.0a1/constraints/py3-linux.txt" \
  "$release_tmp"/wheel/*.whl
cd "$release_tmp"
"$release_tmp/venv/bin/python" -c 'import niep; print(niep.__version__)'
"$release_tmp/venv/bin/niepctl" --help
"$release_tmp/venv/bin/niepd" --help
```

The wheel listing must not contain `OFCONTROLLERS/pox`, `VEM/IMAGES` or
`CLI/CLIMEM`. Runtime asset tests must set `NIEP_ROOT` to the extracted
checkout explicitly.

## Integration proof and tag

From a fresh checkout/VM, run:

```bash
make test
make vm-test-all
git diff --check
git status --short
```

The final status must be clean apart from intentionally untracked local files
that are not part of the release. Only after review approval:

```bash
git tag -a v1.2.0a1 -m "NIEP 1.2.0a1"
git archive --format=tar v1.2.0a1 | tar -tf - >/tmp/niep-release-files.txt
```

The tag must point at the validated commit, never at a dirty worktree.
