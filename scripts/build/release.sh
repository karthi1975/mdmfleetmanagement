#!/usr/bin/env bash
# Release a new firmware version end-to-end from a clean working tree.
#
# Usage:
#   scripts/build/release.sh <version>              # build + stage
#   scripts/build/release.sh <version> --upload     # + upload to fleet-api
#   scripts/build/release.sh <version> --upload --rollout
#                                                   # + start full rollout
#
# Env for --upload / --rollout (any one of):
#   FLEET_API_URL       default https://mdmfleetmanagment.homeadapt.us
#   FLEET_ADMIN_USER    default admin
#   FLEET_ADMIN_PASS    (required for --upload / --rollout)
#
# Exits non-zero on any step failure so CI can wrap it.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="${REPO}/venv"
DEVICE_YAML="${REPO}/esphome/devices/esp32-test.yaml"

if [[ $# -lt 1 ]]; then
  cat >&2 <<USAGE
Usage: $0 <version> [--upload] [--rollout] [--notes "release notes"]

  <version>    semver string, e.g. 18.1.4
  --upload     POST the .ota.bin to fleet-api after build
  --rollout    after upload, trigger a full rollout to every alive
               device not already on <version>  (prompt for confirm)
  --notes TXT  release notes attached to the firmware row

Requires:
  - Python venv at ${VENV} (run scripts/build/dev-setup.sh first)
  - For --upload / --rollout: env FLEET_ADMIN_PASS set
USAGE
  exit 2
fi

VERSION="$1"; shift
UPLOAD=0
ROLLOUT=0
NOTES=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --upload)   UPLOAD=1 ;;
    --rollout)  ROLLOUT=1; UPLOAD=1 ;;
    --notes)    shift; NOTES="$1" ;;
    *) echo "❌ unknown flag: $1"; exit 2 ;;
  esac
  shift
done

if ! [[ "${VERSION}" =~ ^[0-9]+\.[0-9]+\.[0-9]+([.-][A-Za-z0-9]+)?$ ]]; then
  echo "❌ version must be semver (e.g. 18.1.4)"; exit 2
fi

if [[ ! -x "${VENV}/bin/esphome" ]]; then
  echo "❌ venv missing at ${VENV}. Run: ${REPO}/scripts/build/dev-setup.sh"
  exit 1
fi

# ── 1. bump firmware_version in device yaml ────────────────────────
echo "→ Bumping firmware_version to ${VERSION} in esp32-test.yaml"
python3 - "${DEVICE_YAML}" "${VERSION}" <<'PY'
import re, sys, pathlib
path = pathlib.Path(sys.argv[1]); version = sys.argv[2]
src = path.read_text()
new, n = re.subn(
    r'(firmware_version:\s*)"[^"]+"',
    lambda m: f'{m.group(1)}"{version}"', src, count=1
)
if n != 1:
    print("❌ could not find firmware_version line in yaml", file=sys.stderr)
    sys.exit(1)
path.write_text(new)
PY

# ── 2. compile ──────────────────────────────────────────────────────
echo "→ Compiling (ESPHome)…"
cd "${REPO}/esphome/devices"
"${VENV}/bin/esphome" compile esp32-test.yaml
BUILD_DIR="${REPO}/esphome/devices/.esphome/build/esp32-test/.pioenvs/esp32-test"

if [[ ! -f "${BUILD_DIR}/firmware.ota.bin" ]]; then
  echo "❌ build succeeded but firmware.ota.bin is missing"; exit 1
fi

# ── 3. stage under releases/vX.Y.Z/ ────────────────────────────────
REL_DIR="${REPO}/releases/v${VERSION}"
mkdir -p "${REL_DIR}"
cp "${BUILD_DIR}/firmware.ota.bin"     "${REL_DIR}/firmware.ota.bin"
cp "${BUILD_DIR}/firmware.factory.bin" "${REL_DIR}/firmware.factory.bin"
SHA=$(shasum -a 256 "${REL_DIR}/firmware.ota.bin" | awk '{print $1}')
SIZE=$(wc -c < "${REL_DIR}/firmware.ota.bin")
echo
echo "✅ Built v${VERSION}"
echo "   ota bin:     ${REL_DIR}/firmware.ota.bin"
echo "   factory bin: ${REL_DIR}/firmware.factory.bin"
echo "   size:        $(printf "%'d" "${SIZE}") bytes"
echo "   sha256:      ${SHA}"

if [[ ${UPLOAD} -ne 1 ]]; then
  cat <<DONE

Next (manual upload via portal):
  1. Open ${FLEET_API_URL:-https://mdmfleetmanagment.homeadapt.us}
  2. Sign in as admin
  3. "Upload firmware" card → version=${VERSION}, file=${REL_DIR}/firmware.ota.bin
  4. "Trigger OTA rollout" → pick target + devices → Start

Or re-run with --upload (+ --rollout) to do steps 3-4 from CLI.
DONE
  exit 0
fi

# ── 4. upload (--upload) ───────────────────────────────────────────
FLEET_API_URL="${FLEET_API_URL:-https://mdmfleetmanagment.homeadapt.us}"
FLEET_ADMIN_USER="${FLEET_ADMIN_USER:-admin}"
if [[ -z "${FLEET_ADMIN_PASS:-}" ]]; then
  echo "❌ FLEET_ADMIN_PASS env not set; cannot --upload"
  exit 1
fi
if [[ -z "${NOTES}" ]]; then
  NOTES="Release v${VERSION}"
fi

echo
echo "→ Logging in as ${FLEET_ADMIN_USER} @ ${FLEET_API_URL}"
TOKEN=$(curl -sk -X POST "${FLEET_API_URL}/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"${FLEET_ADMIN_USER}\",\"password\":\"${FLEET_ADMIN_PASS}\"}" \
  | python3 -c 'import sys,json; t=json.load(sys.stdin).get("access_token",""); print(t)')
if [[ -z "${TOKEN}" || "${#TOKEN}" -lt 40 ]]; then
  echo "❌ login failed"; exit 1
fi

echo "→ Uploading ${REL_DIR}/firmware.ota.bin as v${VERSION}"
UPLOAD_RESP=$(curl -sk -X POST "${FLEET_API_URL}/api/firmware/" \
  -H "Authorization: Bearer ${TOKEN}" \
  -F "version=${VERSION}" \
  -F "release_notes=${NOTES}" \
  -F "file=@${REL_DIR}/firmware.ota.bin")
echo "   ← ${UPLOAD_RESP}"
echo "${UPLOAD_RESP}" | grep -q '"id":' || { echo "❌ upload response didn't look right"; exit 1; }

# ── 5. rollout (--rollout) ─────────────────────────────────────────
if [[ ${ROLLOUT} -ne 1 ]]; then
  echo "✅ Uploaded. Open the portal to pick targets and start the rollout."
  exit 0
fi

echo
echo "→ Dry-run preview first (no devices selected = full strategy)…"
PREVIEW=$(curl -sk -X POST "${FLEET_API_URL}/api/ota/preview" \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d "{\"target_version\":\"${VERSION}\",\"strategy\":\"full\"}")
echo "   ${PREVIEW}"
TOTAL=$(echo "${PREVIEW}" | python3 -c 'import sys,json; print(json.load(sys.stdin).get("total",0))')
if [[ "${TOTAL}" -eq 0 ]]; then
  echo "ℹ️  Preview shows 0 devices — nothing to roll out (everyone is on ${VERSION} already)."
  exit 0
fi

read -p "→ Start rollout to ${TOTAL} device(s)? [y/N] " CONFIRM
if [[ "${CONFIRM}" != "y" && "${CONFIRM}" != "Y" ]]; then
  echo "Cancelled."; exit 0
fi

echo "→ POST /api/ota/rollout"
curl -sk -X POST "${FLEET_API_URL}/api/ota/rollout" \
  -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \
  -d "{\"target_version\":\"${VERSION}\",\"strategy\":\"full\"}"
echo
echo "✅ Rollout started. Watch the dashboard to monitor device progress."
