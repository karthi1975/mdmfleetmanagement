#!/usr/bin/env bash
# Idempotent developer setup: Python venv + ESPHome + the ESP32 build
# deps that ESPHome itself doesn't install (littlefs-python, fatfs-ng).
# Safe to re-run.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${REPO}/venv"

PY_BIN="${PY_BIN:-python3}"
if ! command -v "${PY_BIN}" >/dev/null 2>&1; then
  echo "❌ ${PY_BIN} not found on PATH. Install Python 3.10+ first."
  exit 1
fi

PY_VER="$("${PY_BIN}" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
echo "→ Using Python ${PY_VER} (${PY_BIN})"

if [[ ! -d "${VENV}" ]]; then
  echo "→ Creating venv at ${VENV}"
  "${PY_BIN}" -m venv "${VENV}"
fi

# shellcheck disable=SC1091
source "${VENV}/bin/activate"

echo "→ Upgrading pip + wheel"
pip install --quiet --upgrade pip wheel

echo "→ Installing ESPHome"
pip install --quiet --upgrade esphome

# ESP-IDF platform needs these Python packages at compile time. ESPHome
# doesn't declare them, so first compiles otherwise fail with
# ModuleNotFoundError: 'littlefs' / 'fatfs'.
echo "→ Installing ESP32 build-time deps (littlefs-python, fatfs-ng)"
pip install --quiet --upgrade "littlefs-python>=0.16.0" "fatfs-ng>=0.1.14"

echo "→ Verifying esphome compile can dry-parse the YAML"
cd "${REPO}/esphome/devices"
"${VENV}/bin/esphome" config esp32-test.yaml >/dev/null

echo
echo "✅ Dev environment ready."
echo "   Activate with:   source ${VENV}/bin/activate"
echo "   Release with:    ${REPO}/scripts/build/release.sh <version>"
