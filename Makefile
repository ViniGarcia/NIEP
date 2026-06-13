VAGRANT_PROVIDER ?= libvirt
NIEP_DIR ?= /home/vagrant/NIEP

.PHONY: vm-up vm-halt vm-reload vm-ssh vm-sync vm-watch vm-cli vm-clean

vm-up:
	vagrant up --provider=$(VAGRANT_PROVIDER)

vm-halt:
	vagrant halt

vm-reload:
	vagrant reload --provision

vm-ssh:
	vagrant ssh

vm-sync:
	vagrant rsync

vm-watch:
	vagrant rsync-auto

vm-cli:
	vagrant ssh -- -t "cd $(NIEP_DIR)/CLI && sudo python3 CLI.py"

vm-clean:
	vagrant ssh -- -t "sudo mn -c; sudo virsh net-destroy vnNIEP || true; sudo ip link set vbrNIEP down || true; sudo brctl delbr vbrNIEP || true"
