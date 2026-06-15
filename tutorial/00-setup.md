# 00 - Setup and Workflow

NIEP manages Mininet, Linux bridges, libvirt, KVM, Docker, and `virsh` directly. Run it inside a Linux VM prepared for that, or on a lab machine where you can use root privileges.

## Vagrant VM

A reproducible option is the Vagrant VM described in `INSTALLATION/VM-DEPLOY.md`:

```bash
vagrant up --provider=libvirt
vagrant ssh
cd /home/vagrant/NIEP
```

If preparing a machine manually, install at least:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-libvirt mininet qemu-kvm qemu-utils \
  libvirt-daemon-system libvirt-clients bridge-utils net-tools iproute2 \
  sshpass docker.io
```

Check that virtualization tools are available:

```bash
sudo virsh list --all
sudo brctl show
sudo docker ps
```

## Fast Vagrant Workflow

With `vagrant-libvirt`, the synced folder may behave as `rsync`. Changes made on the host may not appear inside the VM immediately. You do not need to restart the VM; sync the project instead.

From the repository root:

```bash
make vm-up
make vm-sync
make vm-cli
```

For continuous development, leave one terminal running:

```bash
make vm-watch
```

Available shortcuts:

```bash
make vm-up             # start the VM
make vm-ssh            # open a shell in the VM
make vm-sync           # sync host -> VM once
make vm-watch          # continuously sync host -> VM
make vm-cli            # open sudo python3 CLI.py in the correct directory
make vm-clean          # clean Mininet/bridges/vnNIEP after failures
make check-images      # verify qcow2 files are real images, not Git LFS pointers
make lfs-pull          # download qcow2 files managed by Git LFS
make vm-check-images   # verify the synced VM can see a real TinyCore image
make vm-libvirt-perms  # allow libvirt/QEMU to read NIEP VM images
make vm-reset-tutorial-vm   # remove generated tutorial VMs/domains
```

## Working Directory Rule

Run the CLI from `CLI/`:

```bash
cd /home/vagrant/NIEP/CLI
sudo python3 CLI.py
```

You should see:

```text
niep>
```

All tutorial commands use paths such as `../tutorial/examples/mininet-ping.json` from that prompt.
