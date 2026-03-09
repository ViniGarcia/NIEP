#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  sudo ./INSTALLATION/provision-vm.sh [--repo /path/to/NIEP] [--user username]

Options:
  --repo PATH   Absolute path to NIEP repo inside the VM (default: /home/$USER/NIEP)
  --user NAME   Non-root user that owns the repo and will run setup-py3-dev.sh
EOF
}

TARGET_USER="${SUDO_USER:-${USER}}"
REPO_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_DIR="$2"; shift 2 ;;
    --user) TARGET_USER="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1"; usage; exit 1 ;;
  esac
done

if [[ -z "${REPO_DIR}" ]]; then
  REPO_DIR="/home/${TARGET_USER}/NIEP"
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This script must run with root privileges (use sudo)."
  exit 1
fi

echo "[1/5] Installing system dependencies..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip python3-libvirt \
  qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virt-manager \
  bridge-utils net-tools iproute2 sshpass git curl \
  mininet

echo "[2/5] Enabling libvirt daemon..."
systemctl enable --now libvirtd || true

echo "[3/5] Granting VM user access to virtualization groups..."
usermod -aG libvirt,kvm "${TARGET_USER}" || true

echo "[4/5] Bootstrapping Python 3 virtualenv in repo..."
if [[ ! -d "${REPO_DIR}" ]]; then
  echo "Repo path not found: ${REPO_DIR}"
  exit 1
fi

if [[ -x "${REPO_DIR}/INSTALLATION/setup-py3-dev.sh" ]]; then
  su - "${TARGET_USER}" -c "cd '${REPO_DIR}' && ./INSTALLATION/setup-py3-dev.sh"
else
  su - "${TARGET_USER}" -c "cd '${REPO_DIR}' && chmod +x INSTALLATION/setup-py3-dev.sh && ./INSTALLATION/setup-py3-dev.sh"
fi

echo "[5/5] Done."
cat <<EOF
Provisioning complete.

Important:
  - Log out/in (or reboot) so ${TARGET_USER} gets libvirt/kvm group permissions.
  - Activate venv before running NIEP:
      source ${REPO_DIR}/.venv/bin/activate
  - If not using local POX during migration:
      export NIEP_DISABLE_LOCAL_POX=1
EOF
