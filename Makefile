VAGRANT_PROVIDER ?= libvirt
NIEP_DIR ?= /home/vagrant/NIEP
NIEP_SOCKET ?= /run/niep.sock
NIEPCTL_ARGS ?= status
INTEGRATION_ARGS ?= all
PYTHON ?= .venv/bin/python
BOOTSTRAP_PYTHON ?= python3
NIEP_PYTHON ?= $(NIEP_DIR)/.venv/bin/python
NIEPCTL ?= $(NIEP_DIR)/.venv/bin/niepctl
TEST_REPORT_DIR ?= build/test-results
TEST_JUNIT_XML ?= $(TEST_REPORT_DIR)/junit.xml
TEST_COVERAGE_XML ?= $(TEST_REPORT_DIR)/coverage.xml

.PHONY: vm-up vm-halt vm-reload vm-ssh vm-sync vm-watch vm-cli vm-daemon vm-ctl vm-clean vm-build-iperf3-image vm-build-test-iperf3-image vm-build-local-images vm-libvirt-perms vm-reset-doc-vm vm-reset-tutorial-vm environment doctor vm-doctor check-images check-local-images vm-check-images vm-check-local-images vm-preflight lfs-pull test test-unit test-contract test-static test-command-dispatcher test-errors ci-lint ci-docs ci-history ci-tool-tests ci-check vm-test-static vm-test-command-dispatcher vm-test-errors vm-test-spec vm-test-integration vm-test-iperf-shaper vm-test-all vm-smoke-mininet vm-smoke-vm vm-smoke-click vm-smoke-socket vm-smoke-all

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

environment:
	./INSTALLATION/setup-py3-dev.sh

doctor:
	$(BOOTSTRAP_PYTHON) tools/niep_doctor.py --strict

vm-doctor: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/niep_doctor.py --strict"

vm-cli:
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo $(NIEP_PYTHON) -m niep.interfaces.cli"

vm-daemon:
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo $(NIEP_PYTHON) -m niep.interfaces.niepd --socket $(NIEP_SOCKET)"

vm-ctl:
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEPCTL) --socket $(NIEP_SOCKET) $(NIEPCTL_ARGS)"

vm-clean:
	vagrant ssh -- -t "sudo mn -c; sudo docker rm -f test-alpine test-alpine-router doc-alpine doc-alpine-router doc-iperf-client doc-iperf-server test-iperf-client test-iperf-server || true; sudo virsh net-destroy vnNIEP || true; sudo ip link set vbrNIEP down || true; sudo brctl delbr vbrNIEP || true"

vm-build-iperf3-image: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR)/tutorial/examples/containers/iperf3 && sudo docker compose build"

vm-build-test-iperf3-image: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR)/tests/fixtures/containers/iperf3 && sudo docker compose build"

vm-build-local-images: vm-build-iperf3-image vm-build-test-iperf3-image
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/niep_doctor.py --check-local-images"


vm-libvirt-perms:
	vagrant ssh -- -t "sudo chmod o+x /home/vagrant $(NIEP_DIR) $(NIEP_DIR)/VEM; sudo chmod -R a+rX $(NIEP_DIR)/VEM/IMAGES"

vm-reset-doc-vm:
	vagrant ssh -- -t "sudo docker rm -f test-alpine test-alpine-router doc-alpine doc-alpine-router doc-iperf-client doc-iperf-server test-iperf-client test-iperf-server || true; sudo ip link del ct-alp0 || true; sudo ip link del ct-rtr0 || true; sudo ip link del ct-rtr1 || true; sudo ip link del ct-doc0 || true; sudo ip link del ct-drtr0 || true; sudo ip link del ct-drtr1 || true; sudo ip link del ct-icli0 || true; sudo ip link del ct-isrv0 || true; sudo ip link del ct-tcli0 || true; sudo ip link del ct-tsrv0 || true; sudo virsh destroy doc-tinycore || true; sudo virsh undefine doc-tinycore || true; sudo virsh destroy doc-tinycore-link || true; sudo virsh undefine doc-tinycore-link || true; sudo virsh destroy doc-click-forward || true; sudo virsh undefine doc-click-forward || true; sudo virsh destroy doc-click-shaper || true; sudo virsh undefine doc-click-shaper || true; sudo virsh destroy test-click-shaper-vm || true; sudo virsh undefine test-click-shaper-vm || true; sudo virsh destroy click-forward || true; sudo virsh undefine click-forward || true; sudo virsh destroy click-shaper || true; sudo virsh undefine click-shaper || true; sudo virsh destroy test-click-shaper || true; sudo virsh undefine test-click-shaper || true; sudo rm -rf $(NIEP_DIR)/VEM/IMAGES/doc-tinycore $(NIEP_DIR)/VEM/IMAGES/doc-tinycore-link $(NIEP_DIR)/VEM/IMAGES/doc-click-forward $(NIEP_DIR)/VEM/IMAGES/doc-click-shaper $(NIEP_DIR)/VEM/IMAGES/test-click-shaper-vm $(NIEP_DIR)/VEM/IMAGES/click-forward $(NIEP_DIR)/VEM/IMAGES/click-shaper $(NIEP_DIR)/VEM/IMAGES/test-click-shaper"


vm-reset-tutorial-vm: vm-reset-doc-vm

check-images:
	$(BOOTSTRAP_PYTHON) tools/niep_doctor.py --check-images

check-local-images:
	$(BOOTSTRAP_PYTHON) tools/niep_doctor.py --check-local-images

vm-check-images: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/niep_doctor.py --check-images"

vm-check-local-images: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/niep_doctor.py --check-local-images"

vm-preflight: vm-doctor vm-check-images

lfs-pull:
	git lfs install --skip-repo
	git lfs pull --include='VEM/IMAGES/*.qcow2'

test-static:
	$(PYTHON) tools/check_static.py

test-command-dispatcher:
	$(PYTHON) -m pytest tests/test_command_dispatcher.py -m unit

test-unit:
	$(PYTHON) -m pytest -m "unit and not privileged"

test-contract:
	$(PYTHON) -m pytest -m "contract and not privileged"

test: test-static
	mkdir -p "$(TEST_REPORT_DIR)"
	$(PYTHON) -m pytest -m "not privileged" --cov --cov-report=term-missing --cov-report=xml:"$(TEST_COVERAGE_XML)" --junitxml="$(TEST_JUNIT_XML)"

ci-lint:
	$(PYTHON) tools/ci/check_style.py

ci-docs:
	$(PYTHON) tools/ci/check_docs.py

ci-history:
	$(PYTHON) tools/ci/check_privileged_history.py --history docs/ci/privileged-history.json

ci-tool-tests:
	$(PYTHON) -m pytest tests/test_ci_tools.py tests/test_privileged_checks.py -m unit

ci-check: ci-lint ci-docs ci-history ci-tool-tests

test-errors:
	$(PYTHON) tests/check_teardown.py

vm-test-static: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/check_static.py"

vm-test-command-dispatcher: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/check_command_dispatcher.py"

vm-test-errors: vm-sync
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tests/check_teardown.py && sudo $(NIEP_PYTHON) tests/check_error_handling.py"

vm-test-spec: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/check_specs.py"

vm-test-integration: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo $(NIEP_PYTHON) tests/integration/run_topology_tests.py $(INTEGRATION_ARGS)"

vm-test-iperf-shaper: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR)/tutorial/examples/containers/iperf3 && sudo docker compose build"
	vagrant ssh -- -t "cd $(NIEP_DIR)/tests/fixtures/containers/iperf3 && sudo docker compose build"
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/niep_doctor.py --check-local-images"
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo $(NIEP_PYTHON) tests/integration/run_topology_tests.py iperf-click-shaper"

vm-test-all: vm-test-static vm-test-command-dispatcher vm-test-errors vm-test-spec vm-test-integration vm-smoke-all

vm-smoke-mininet: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/smoke/run_cli_smoke.py mininet"

vm-smoke-vm: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/smoke/run_cli_smoke.py vm"

vm-smoke-click: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/smoke/run_cli_smoke.py click"

vm-smoke-socket: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo $(NIEP_PYTHON) tools/smoke/run_socket_smoke.py"

vm-smoke-all: vm-preflight vm-reset-tutorial-vm vm-libvirt-perms
	vagrant ssh -- -t "cd $(NIEP_DIR) && $(NIEP_PYTHON) tools/smoke/run_cli_smoke.py all"
	vagrant ssh -- -t "cd $(NIEP_DIR) && sudo $(NIEP_PYTHON) tools/smoke/run_socket_smoke.py"
