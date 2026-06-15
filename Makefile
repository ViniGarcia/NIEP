VAGRANT_PROVIDER ?= libvirt
NIEP_DIR ?= /home/vagrant/NIEP
NIEP_SOCKET ?= /tmp/niep.sock
NIEPCTL_ARGS ?= status
INTEGRATION_ARGS ?= all

.PHONY: vm-up vm-halt vm-reload vm-ssh vm-sync vm-watch vm-cli vm-daemon vm-ctl vm-clean vm-libvirt-perms vm-reset-doc-vm vm-reset-tutorial-vm check-images vm-check-images lfs-pull test-static test-command-dispatcher vm-test-static vm-test-command-dispatcher vm-test-spec vm-test-integration vm-test-all vm-smoke-mininet vm-smoke-vm vm-smoke-click vm-smoke-socket vm-smoke-all

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

vm-daemon:
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo python3 tools/niepd.py --socket $(NIEP_SOCKET)"

vm-ctl:
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/niepctl.py --socket $(NIEP_SOCKET) $(NIEPCTL_ARGS)"

vm-clean:
	vagrant ssh -- -t "sudo mn -c; sudo docker rm -f test-alpine doc-alpine || true; sudo virsh net-destroy vnNIEP || true; sudo ip link set vbrNIEP down || true; sudo brctl delbr vbrNIEP || true"


vm-libvirt-perms:
	vagrant ssh -- -t "sudo chmod o+x /home/vagrant $(NIEP_DIR) $(NIEP_DIR)/VEM; sudo chmod -R a+rX $(NIEP_DIR)/VEM/IMAGES"

vm-reset-doc-vm:
	vagrant ssh -- -t "sudo docker rm -f test-alpine doc-alpine || true; sudo ip link del ct-alp0 || true; sudo ip link del ct-doc0 || true; sudo virsh destroy doc-tinycore || true; sudo virsh undefine doc-tinycore || true; sudo virsh destroy doc-tinycore-link || true; sudo virsh undefine doc-tinycore-link || true; sudo virsh destroy doc-click-forward || true; sudo virsh undefine doc-click-forward || true; sudo virsh destroy click-forward || true; sudo virsh undefine click-forward || true; sudo rm -rf $(NIEP_DIR)/VEM/IMAGES/doc-tinycore $(NIEP_DIR)/VEM/IMAGES/doc-tinycore-link $(NIEP_DIR)/VEM/IMAGES/doc-click-forward $(NIEP_DIR)/VEM/IMAGES/click-forward"


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

test-command-dispatcher:
	python3 -m py_compile TOPO-MAN/Command.py TOPO-MAN/SocketServer.py tools/niepd.py tools/niepctl.py tools/check_command_dispatcher.py tools/smoke/run_socket_smoke.py tests/integration/run_topology_tests.py

vm-test-static: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/check_static.py"

vm-test-command-dispatcher: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/check_command_dispatcher.py"

vm-test-spec: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/check_specs.py"

vm-test-integration: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo python3 tests/integration/run_topology_tests.py $(INTEGRATION_ARGS)"

vm-test-all: vm-test-static vm-test-command-dispatcher vm-test-spec vm-test-integration vm-smoke-all

vm-smoke-mininet: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py mininet"

vm-smoke-vm: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py vm"

vm-smoke-click: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py click"

vm-smoke-socket: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo python3 tools/smoke/run_socket_smoke.py"

vm-smoke-all: vm-sync vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && python3 tools/smoke/run_cli_smoke.py all"
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo python3 tools/smoke/run_socket_smoke.py"
