#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage:
  sudo ./INSTALLATION/installer.sh [--repo /path/to/NIEP] [--user username]

This is the public installer entry point for NIEP's Python 3 environment.
It delegates to INSTALLATION/provision-vm.sh, the same provisioning script used
by the Vagrant VM, so manual and Vagrant installs stay reproducible.

Options:
  --repo PATH   Absolute path to the NIEP repository (default: current repo)
  --user NAME   Non-root user that owns the repository
  -h, --help    Show this help message
USAGE
}

has_repo_arg=0
for arg in "$@"; do
  case "$arg" in
    -h|--help)
      usage
      exit 0
      ;;
    --repo)
      has_repo_arg=1
      ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "This script must run with root privileges (use sudo)."
  exit 1
fi

if [[ "${has_repo_arg}" == "1" ]]; then
  exec "${ROOT_DIR}/INSTALLATION/provision-vm.sh" "$@"
fi

exec "${ROOT_DIR}/INSTALLATION/provision-vm.sh" --repo "${ROOT_DIR}" "$@"
