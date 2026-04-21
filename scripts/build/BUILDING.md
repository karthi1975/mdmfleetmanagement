# Building and Releasing Firmware

How any engineer on the team produces a new firmware binary and gets
it onto the fleet.

## One-time setup (~5 min, ~500 MB download)

Python 3.10+ is required.

```
cd /path/to/MDM_ESP32
scripts/build/dev-setup.sh
```

The script creates `venv/` at the repo root, installs ESPHome, and
adds the two ESP32 build-time Python packages (`littlefs-python`,
`fatfs-ng`) that ESPHome doesn't declare itself. The first compile
also downloads the pioarduino toolchain (~500 MB) into
`~/.platformio/` — that only happens once.

Re-running `dev-setup.sh` is safe; it short-circuits anything that's
already installed.

## Releasing a new version (30–60 seconds after toolchain cache)

```
# build + stage under releases/v18.1.4/
scripts/build/release.sh 18.1.4

# ...or build AND upload to the fleet-api
FLEET_ADMIN_PASS=•••• scripts/build/release.sh 18.1.4 --upload

# ...or build, upload, and (after a preview + confirm) start rollout
FLEET_ADMIN_PASS=•••• scripts/build/release.sh 18.1.4 --upload --rollout
```

What `release.sh` does, step by step:

1. Rewrites `firmware_version: "X.Y.Z"` in
   `esphome/devices/esp32-test.yaml` to the version you passed.
2. Runs `esphome compile esp32-test.yaml`.
3. Copies `firmware.ota.bin` + `firmware.factory.bin` into
   `releases/v<version>/`.
4. Prints the file paths, size, and SHA-256.
5. `--upload` — logs in with `FLEET_ADMIN_USER` / `FLEET_ADMIN_PASS`
   and `POST`s `firmware.ota.bin` to `/api/firmware/` on
   `FLEET_API_URL`.
6. `--rollout` — calls `/api/ota/preview` first, shows how many
   devices would be hit, prompts for confirmation, then
   `POST`s `/api/ota/rollout` with strategy=full.

## Manual alternative (no CLI)

If you don't have a dev box set up, any engineer who does can hand
you `firmware.ota.bin` directly. Then:

1. Open `https://mdmfleetmanagment.homeadapt.us/` as admin.
2. **Upload firmware** card → type the version → choose the file →
   **Upload firmware**.
3. **Trigger OTA rollout** → pick devices with filters + chips +
   saved groups → **Preview targets** → **Start OTA rollout now**.

No shell, no git, no Python.

## Env vars

| Var | Default | Used by |
|---|---|---|
| `PY_BIN` | `python3` | `dev-setup.sh` to pick which Python to venv against |
| `FLEET_API_URL` | `https://mdmfleetmanagment.homeadapt.us` | `release.sh --upload` |
| `FLEET_ADMIN_USER` | `admin` | `release.sh --upload` |
| `FLEET_ADMIN_PASS` | *(required for --upload)* | `release.sh --upload` |

Put `FLEET_ADMIN_PASS` in your shell's secret manager, e.g.:

```
# macOS Keychain
export FLEET_ADMIN_PASS=$(security find-generic-password -a $USER -s fleet-admin -w)
```

## Version numbering

Semver. Patch bumps for bug fixes and "unification" re-releases, minor
bumps for new sensor/behavior, major bumps for breaking provisioning
or NVS schema changes.

## Audit trail

Every firmware upload and rollout triggered via the dashboard OR the
CLI is recorded in `audit_log` (visible as a panel in Grafana). The
CLI's `user_id` on upload is whatever admin account is in
`FLEET_ADMIN_USER` — so use personal admin accounts, not a shared one,
if compliance matters.

## Troubleshooting

### `ModuleNotFoundError: No module named 'littlefs'` or `'fatfs'`
Dev-setup was not run (or was run in a different venv).
```
scripts/build/dev-setup.sh
```

### `Could not connect to ESP32: Timed out waiting for packet header`
You're USB-flashing, not OTA-ing. Hold the BOOT button on the board
during the first connection. Unrelated to `release.sh`.

### `upload failed: 409 Version already exists`
The fleet-api rejects re-upload of the same version. Bump the version
and re-run, or delete the existing firmware row first (advanced:
`DELETE FROM firmware_versions WHERE version='…'` on the droplet —
only safe if no device ever booted that binary).

### `login failed`
Check `FLEET_ADMIN_PASS`. Default seeded password is `admin123`; if
it was rotated, use the current value.

### Compile succeeds but OTA says "Version not found"
Uploading used a different version string than the one baked into the
binary. `release.sh` keeps them consistent; if you compile manually,
double-check the yaml and the `--version` flag to curl match.
