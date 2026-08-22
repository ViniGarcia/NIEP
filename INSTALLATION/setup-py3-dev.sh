#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv"
REQ_FILE="$ROOT_DIR/INSTALLATION/requirements-py3-min.txt"
DEV_REQ_FILE="$ROOT_DIR/requirements-dev.txt"
INTEGRATION_REQ_FILE="$ROOT_DIR/requirements-integration.txt"
LOCK_FILE="$ROOT_DIR/constraints/py3-linux.txt"
SKIP_PIP_INSTALL="${SKIP_PIP_INSTALL:-0}"
SKIP_PIP_UPGRADE="${SKIP_PIP_UPGRADE:-0}"
VENV_SYSTEM_SITE_PACKAGES="${VENV_SYSTEM_SITE_PACKAGES:-0}"

case "$VENV_SYSTEM_SITE_PACKAGES" in
  0) EXPECTED_SYSTEM_SITE_PACKAGES="false" ;;
  1) EXPECTED_SYSTEM_SITE_PACKAGES="true" ;;
  *)
    echo "ERROR: VENV_SYSTEM_SITE_PACKAGES must be 0 or 1."
    exit 1
    ;;
esac

echo "[1/4] Checking supported Python (3.10, 3.11 or 3.12)..."
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "ERROR: $PYTHON_BIN was not found."
  exit 1
fi
PYTHON_VERSION="$($PYTHON_BIN -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
case "$PYTHON_VERSION" in
  3.10|3.11|3.12) ;;
  *)
    echo "ERROR: Python $PYTHON_VERSION is unsupported; use Python 3.10, 3.11 or 3.12."
    exit 1
    ;;
esac
"$PYTHON_BIN" --version

if [[ ! -f "$LOCK_FILE" ]]; then
  echo "ERROR: dependency lock is missing: $LOCK_FILE"
  exit 1
fi

if [[ -x "$VENV_DIR/bin/python" ]]; then
  VENV_VERSION="$($VENV_DIR/bin/python -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || true)"
  ACTUAL_SYSTEM_SITE_PACKAGES="$(sed -n 's/^include-system-site-packages = //p' "$VENV_DIR/pyvenv.cfg" 2>/dev/null || true)"
  if [[ "$VENV_VERSION" != "$PYTHON_VERSION" ]]; then
    echo "Existing .venv uses Python ${VENV_VERSION:-unknown}; recreating it with $PYTHON_VERSION..."
    rm -rf "$VENV_DIR"
  elif [[ "$ACTUAL_SYSTEM_SITE_PACKAGES" != "$EXPECTED_SYSTEM_SITE_PACKAGES" ]]; then
    echo "Existing .venv has include-system-site-packages=${ACTUAL_SYSTEM_SITE_PACKAGES:-unknown}; recreating it with ${EXPECTED_SYSTEM_SITE_PACKAGES}..."
    rm -rf "$VENV_DIR"
  fi
elif [[ -e "$VENV_DIR" ]]; then
  echo "Existing .venv is not a usable virtualenv; recreating it..."
  rm -rf "$VENV_DIR"
fi

echo "[2/4] Creating or updating virtual environment at $VENV_DIR..."
VENV_ARGS=()
if [[ "$VENV_SYSTEM_SITE_PACKAGES" == "1" ]]; then
  VENV_ARGS+=(--system-site-packages)
fi
"$PYTHON_BIN" -m venv "${VENV_ARGS[@]}" "$VENV_DIR"
VENV_PY="$VENV_DIR/bin/python"

if [[ "$SKIP_PIP_UPGRADE" == "1" || "$SKIP_PIP_INSTALL" == "1" ]]; then
  echo "[3/4] Skipping pinned packaging-tool update."
else
  echo "[3/4] Installing pinned pip/setuptools/wheel..."
  "$VENV_PY" -m pip install --upgrade \
    --constraint "$LOCK_FILE" \
    pip setuptools wheel
fi

if [[ "$SKIP_PIP_INSTALL" == "1" ]]; then
  echo "[4/4] SKIP_PIP_INSTALL=1, skipping dependency installation."
else
  # Install the base project dependencies and the two supported extras.  Base
  # dependencies in [project] provide the application set; dev and integration
  # are the optional groups.
  USE_PROJECT_GROUPS=0
  if [[ -f "$ROOT_DIR/pyproject.toml" ]] \
    && grep -Eq '^\[project\][[:space:]]*$' "$ROOT_DIR/pyproject.toml" \
    && grep -Eq '^\[project\.optional-dependencies\][[:space:]]*$' "$ROOT_DIR/pyproject.toml" \
    && grep -Eq '^dev[[:space:]]*=' "$ROOT_DIR/pyproject.toml" \
    && grep -Eq '^integration[[:space:]]*=' "$ROOT_DIR/pyproject.toml"; then
    USE_PROJECT_GROUPS=1
  fi

  if [[ "$USE_PROJECT_GROUPS" == "1" ]]; then
    echo "[4/4] Installing base project dependencies plus extras dev,integration..."
    "$VENV_PY" -m pip install --constraint "$LOCK_FILE" \
      --editable "${ROOT_DIR}[dev,integration]"
  else
    echo "[4/4] Installing base and legacy dev,integration requirements under pinned constraints..."
    REQUIREMENT_ARGS=(--requirement "$REQ_FILE" --requirement "$DEV_REQ_FILE")
    if [[ -f "$INTEGRATION_REQ_FILE" ]]; then
      REQUIREMENT_ARGS+=(--requirement "$INTEGRATION_REQ_FILE")
    fi
    "$VENV_PY" -m pip install --constraint "$LOCK_FILE" "${REQUIREMENT_ARGS[@]}"
  fi
  "$VENV_PY" -m pip check
fi

cat <<EOF
Environment ready (Python $PYTHON_VERSION).

Activate it with:
  source $VENV_DIR/bin/activate

The locked dependency set is: $LOCK_FILE
Virtualenv system packages enabled: $EXPECTED_SYSTEM_SITE_PACKAGES
System prerequisites (Docker, libvirt/KVM, Mininet, bridges and Git LFS) are
checked separately with: python3 tools/niep_doctor.py --strict
EOF
