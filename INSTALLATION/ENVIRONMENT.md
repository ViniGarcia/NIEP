# NIEP reproducible environment

The supported development matrix is Python 3.10, 3.11 or 3.12 on Ubuntu
22.04.  The Vagrant definition pins `generic/ubuntu2204` to box version
`4.3.12`, the version installed on the reference host.  The box is the
baseline for system packages (libvirt/KVM, Docker, Mininet, bridges and Git
LFS); package versions are recorded by the provisioning log and should be
updated by changing the box deliberately.

## Host or Vagrant setup

```bash
vagrant up --provider=libvirt
vagrant provision                 # safe to repeat
make doctor                       # host checks
make vm-doctor                    # checks inside the VM
make check-images                 # LFS qcow2 and Docker input checks
```

For a host install, run `sudo INSTALLATION/installer.sh --user "$USER"` from
the repository.  The installer and Vagrant call the same idempotent
`provision-vm.sh`; it installs system packages, enables services, grants the
required groups and updates `.venv` instead of layering a second environment.
Log out and back in after the first run so group membership is refreshed.

The setup script uses `constraints/py3-linux.txt`.  It installs the base
project dependencies plus the `dev` and `integration` extras in editable mode;
if project metadata is unavailable it falls back to the base and legacy
requirement files.  There is no separate `runtime` extra.  Set
`SKIP_PIP_INSTALL=1` only for offline/system-package checks.

On a developer host, the virtualenv is isolated from system packages. The VM
provisioner sets `VENV_SYSTEM_SITE_PACKAGES=1` because Ubuntu supplies the
Mininet and libvirt Python bindings that are not distributed as supported pip
packages. The setup script records and reconciles this mode in `pyvenv.cfg`,
so switching modes recreates the environment instead of silently leaking a
different import path.

## Diagnostics and recovery

`python3 tools/niep_doctor.py --strict` (or `make doctor`) prints a status and
remediation for Python, `.venv`, Docker, libvirt/KVM, Mininet, Open vSwitch,
bridges, Git LFS and repository images.  Use `--json` for automation.  A
missing LFS object, `qemu-img`, or immutable Alpine cache entry is a hard
failure for `--check-images`; VM provisioning caches that exact digest.
Local Docker build products are optional during the normal diagnosis. Check
them explicitly with `python3 tools/niep_doctor.py --check-local-images`; when
requested, an absent local image is a hard failure.

The Python wheel deliberately excludes large or external deployment assets.
Editable installs find the checkout automatically; wheel deployments must set
`NIEP_ROOT` to a checkout containing `VEM/`, `CONFS/`, `CLI/CLIMEM/` and, when
enabled, `OFCONTROLLERS/pox/`. Asset consumers validate this root lazily and
return a clear `NIEPPathError` instead of deriving paths from the current
working directory.

If a VM has stale networking after a failed experiment, use the existing
`make vm-clean`, then run `vagrant provision`; do not destroy a shared VM as a
first recovery step.  `vagrant destroy -f` is appropriate only for a
disposable VM.  Re-run provisioning after cleanup; it is safe and does not
duplicate groups, services or symlinks.

See `IMAGE-LOCKS.md` and `../constraints/README.md` for controlled update
procedures.
