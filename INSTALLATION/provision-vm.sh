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
    --repo)
      [[ $# -ge 2 ]] || { echo "--repo requires a path" >&2; exit 2; }
      REPO_DIR="$2"
      shift 2
      ;;
    --user)
      [[ $# -ge 2 ]] || { echo "--user requires a name" >&2; exit 2; }
      TARGET_USER="$2"
      shift 2
      ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "${REPO_DIR}" ]]; then
  REPO_DIR="/home/${TARGET_USER}/NIEP"
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This script must run with root privileges (use sudo)." >&2
  exit 1
fi
if ! id "${TARGET_USER}" >/dev/null 2>&1; then
  echo "Target user does not exist: ${TARGET_USER}" >&2
  exit 1
fi
if [[ ! -d "${REPO_DIR}" ]]; then
  echo "Repo path not found: ${REPO_DIR}" >&2
  exit 1
fi

echo "[1/7] Installing system dependencies (safe to repeat)..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip python3-libvirt python3-pexpect \
  qemu-kvm qemu-utils libvirt-daemon-system libvirt-clients virt-manager \
  bridge-utils net-tools iproute2 sshpass git git-lfs curl \
  docker.io docker-compose-v2 openvswitch-switch mininet

enable_service() {
  local service="$1"
  if command -v systemctl >/dev/null 2>&1; then
    if ! systemctl enable --now "$service"; then
      echo "WARNING: could not start ${service}; run tools/niep_doctor.py after fixing the service." >&2
    fi
  else
    echo "WARNING: systemctl is unavailable; start ${service} before integration tests." >&2
  fi
}

echo "[2/7] Enabling libvirt, Docker and Open vSwitch daemons..."
enable_service libvirtd
enable_service docker
enable_service openvswitch-switch

echo "[3/7] Caching the immutable Docker fixture base..."
IMAGE_LOCK_FILE="${REPO_DIR}/INSTALLATION/image-locks.env"
ALPINE_REFERENCE="$(sed -n 's/^NIEP_ALPINE_REFERENCE=//p' "${IMAGE_LOCK_FILE}" 2>/dev/null || true)"
if [[ ! "${ALPINE_REFERENCE}" =~ ^[^[:space:]@]+:[^[:space:]@]+@sha256:[0-9a-f]{64}$ ]]; then
  echo "ERROR: invalid or missing NIEP_ALPINE_REFERENCE in ${IMAGE_LOCK_FILE}" >&2
  exit 1
fi
if ! docker image inspect "${ALPINE_REFERENCE}" >/dev/null 2>&1; then
  docker pull "${ALPINE_REFERENCE}"
fi

echo "[4/7] Creating groups and granting ${TARGET_USER} access..."
for group in libvirt kvm docker; do
  if ! getent group "$group" >/dev/null; then
    echo "ERROR: expected system group is missing after package installation: $group" >&2
    exit 1
  fi
done
getent group niep >/dev/null || groupadd --system niep
usermod -aG libvirt,kvm,docker,niep "${TARGET_USER}"

echo "[5/7] Initializing Git LFS for ${TARGET_USER}..."
if command -v git-lfs >/dev/null 2>&1; then
  su - "${TARGET_USER}" -c "git lfs install --skip-repo" || {
    echo "WARNING: git lfs install failed; make check-images will report it." >&2
  }
else
  echo "WARNING: git-lfs was not installed; make check-images will fail until it is available." >&2
fi

echo "[6/7] Creating or updating the Python virtualenv..."
chmod +x "${REPO_DIR}/INSTALLATION/setup-py3-dev.sh" "${REPO_DIR}/tools/niep_doctor.py"
printf -v QUOTED_REPO '%q' "${REPO_DIR}"
su - "${TARGET_USER}" -c "cd ${QUOTED_REPO} && VENV_SYSTEM_SITE_PACKAGES=1 ./INSTALLATION/setup-py3-dev.sh"

echo "[7/7] Installing stable local command links..."
chmod +x "${REPO_DIR}/tools/niepctl"
ln -sfn "${REPO_DIR}/.venv/bin/niepctl" /usr/local/bin/niepctl
ln -sfn "${REPO_DIR}/tools/niep_doctor.py" /usr/local/bin/niep-doctor

cat <<EOF
Provisioning complete and safe to repeat.

Important:
  - Log out/in (or reboot) so ${TARGET_USER} gets libvirt/kvm/docker/niep group permissions.
  - Activate venv before running NIEP:
      source ${REPO_DIR}/.venv/bin/activate
  - Diagnose all prerequisites with:
      python3 ${REPO_DIR}/tools/niep_doctor.py --strict
  - If not using local POX during migration:
      export NIEP_DISABLE_LOCAL_POX=1
EOF
