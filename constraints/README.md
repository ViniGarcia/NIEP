# Python constraints

`py3-linux.txt` is the reviewed dependency lock used by the Ubuntu 22.04
Vagrant image and by `INSTALLATION/setup-py3-dev.sh`.  It contains exact
versions for the base project, development and integration Python dependencies
(and their transitive dependencies), so a fresh virtualenv can be recreated
with the same resolver result.

The lock is deliberately a constraints file rather than a replacement for
the dependency declarations.  The canonical declarations live in the
project metadata (and the legacy `requirements*.txt` files remain the setup
fallback during the packaging migration).

## Updating the lock

1. Change the dependency declaration first and run the unit/contract suite.
2. In a clean Python 3.10, 3.11 and 3.12 environment, install the base project
   dependencies plus the `dev` and `integration` extras with `pip-compile` (or
   an equivalent pinned resolver).
3. Regenerate this file with hashes when the target index is stable, run
   `python -m pip check`, and run `make doctor` plus the non-privileged tests.
4. Review the complete diff, especially packages with native extensions, and
   record the resolver/index/date in the change that updates the lock.

The supported matrix is Python 3.10--3.12 on Ubuntu 22.04 (the pinned
`generic/ubuntu2204` Vagrant box).  A lock update is intentional maintenance;
do not silently refresh it during provisioning.  If a Python minor version
needs a different wheel, add a separate constraints file and select it from
the setup script rather than weakening the pins.
