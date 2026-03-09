#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
REQ_FILE="$ROOT_DIR/INSTALLATION/requirements-py3-min.txt"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"
SKIP_PIP_UPGRADE="${SKIP_PIP_UPGRADE:-0}"

echo "[1/4] Checking python3..."
command -v python3 >/dev/null
python3 --version

echo "[2/4] Creating virtual environment at $VENV_DIR..."
python3 -m venv "$VENV_DIR"

if [[ "$SKIP_PIP_UPGRADE" == "1" || "$SKIP_PIP_INSTALL" == "1" ]]; then
  echo "[3/4] Skipping pip/setuptools/wheel upgrade."
else
  echo "[3/4] Upgrading base packaging tools..."
  "$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel || {
    echo "Warning: failed to upgrade packaging tools (likely no internet). Continuing."
  }
fi

if [[ "$SKIP_PIP_INSTALL" == "1" ]]; then
  echo "[4/4] SKIP_PIP_INSTALL=1, skipping dependency installation."
else
  echo "[4/4] Installing Python dependencies from $REQ_FILE..."
  "$VENV_DIR/bin/pip" install -r "$REQ_FILE"
fi

cat <<'EOF'
Environment ready.

Activate it with:
  source .venv/bin/activate

Notes:
  - System dependencies (mininet/libvirt/qemu/bridge-utils) must be installed via apt.
  - libvirt Python bindings are typically installed via distro packages, not pip.
EOF
