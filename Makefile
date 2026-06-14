VAGRANT_PROVIDER ?= libvirt
NIEP_DIR ?= /home/vagrant/NIEP

.PHONY: vm-up vm-halt vm-reload vm-ssh vm-sync vm-watch vm-cli vm-clean vm-libvirt-perms vm-reset-doc-vm vm-reset-tutorial-vm check-images vm-check-images lfs-pull test-static vm-test-static vm-smoke-mininet vm-smoke-vm vm-smoke-click vm-smoke-all

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


vm-libvirt-perms:
	vagrant ssh -- -t "sudo chmod o+x /home/vagrant $(NIEP_DIR) $(NIEP_DIR)/VEM; sudo chmod -R a+rX $(NIEP_DIR)/VEM/IMAGES"

vm-reset-doc-vm:
	vagrant ssh -- -t "sudo virsh destroy doc-tinycore || true; sudo virsh undefine doc-tinycore || true; sudo virsh destroy doc-tinycore-link || true; sudo virsh undefine doc-tinycore-link || true; sudo virsh destroy doc-click-forward || true; sudo virsh undefine doc-click-forward || true; sudo virsh destroy click-forward || true; sudo virsh undefine click-forward || true; sudo rm -rf $(NIEP_DIR)/VEM/IMAGES/doc-tinycore $(NIEP_DIR)/VEM/IMAGES/doc-tinycore-link $(NIEP_DIR)/VEM/IMAGES/doc-click-forward $(NIEP_DIR)/VEM/IMAGES/click-forward"


vm-reset-tutorial-vm: vm-reset-doc-vm

check-images:
	@if grep -q "git-lfs.github.com/spec" VEM/IMAGES/tinycore12.qcow2 VEM/IMAGES/click-on-osv.qcow2; then 		echo "ERROR: qcow2 image files are still Git LFS pointer files."; 		echo "Run: git lfs install && git lfs pull --include='VEM/IMAGES/*.qcow2'"; 		exit 1; 	fi
	@file VEM/IMAGES/tinycore12.qcow2 VEM/IMAGES/click-on-osv.qcow2

vm-check-images:
	vagrant ssh -- -t "cd $(NIEP_DIR) && if grep -q 'git-lfs.github.com/spec' VEM/IMAGES/tinycore12.qcow2 VEM/IMAGES/click-on-osv.qcow2; then echo 'ERROR: qcow2 image files are still Git LFS pointer files.'; exit 1; fi; qemu-img info VEM/IMAGES/tinycore12.qcow2"

lfs-pull:
	git lfs install
	git lfs pull --include='VEM/IMAGES/*.qcow2'

test-static:
	python3 tools/check_static.py

vm-test-static: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/check_static.py"

vm-smoke-mininet: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py mininet"

vm-smoke-vm: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py vm"

vm-smoke-click: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py click"

vm-smoke-all: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py all"
