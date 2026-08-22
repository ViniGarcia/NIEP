# Vagrant deployment

NIEP's reproducible VM uses the libvirt provider and the pinned
`generic/ubuntu2204` box version `4.3.12`.

```bash
vagrant up --provider=libvirt
vagrant provision
vagrant ssh
cd /home/vagrant/NIEP
source .venv/bin/activate
python3 tools/niep_doctor.py --strict
```

The synced repository is provisioned by `INSTALLATION/provision-vm.sh`.
Provisioning can be repeated after `vagrant rsync`; it installs only missing
system packages, enables libvirt, Docker and Open vSwitch, uses the existing
virtualenv, and keeps the `vagrant` user in the `libvirt`, `kvm`, `docker` and
`niep` groups.  A fresh login is needed for new group membership to take
effect.

To intentionally adopt a newer box, set `NIEP_BOX_VERSION` for a disposable
VM, verify the new image and then update the default in `Vagrantfile` and this
document.  Do not change the box implicitly during normal provisioning.
