#!/usr/bin/env bash
# Collect best-effort host, guest and runtime state after integration tests.

set -u

output_dir="${1:-build/ci-diagnostics}"
mkdir -p "$output_dir"

capture() {
  local name="$1"
  shift
  "$@" >"$output_dir/$name.txt" 2>&1 || true
}

capture host-uname uname -a
capture host-ip-link ip -d link show
capture host-ip-address ip -br address
capture host-ip-route ip route show table all
capture host-lsmod lsmod
capture docker-info sudo -n docker info
capture docker-containers sudo -n docker ps -a --no-trunc
capture docker-networks sudo -n docker network ls
capture libvirt-domains sudo -n virsh list --all
capture libvirt-networks sudo -n virsh net-list --all
capture vagrant-status vagrant status
capture lfs-status git lfs status

if command -v vagrant >/dev/null 2>&1; then
  capture guest-status vagrant ssh -- -t "hostname; id; ip -br address; ip route; sudo virsh list --all; sudo docker ps -a"
fi

date -u +%Y-%m-%dT%H:%M:%SZ >"$output_dir/collected-at.txt"
echo "diagnostics written to $output_dir"
