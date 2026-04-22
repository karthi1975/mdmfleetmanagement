% tetradapt HomeAdapt — Fleet Integration Contract
% v1.0 · 2026-04-21

**Purpose.** This document defines the protocol contract every ESP32 firmware
must satisfy to participate in the tetradapt HomeAdapt fleet. Any firmware that
implements this contract — regardless of framework (ESPHome, Arduino, ESP-IDF,
Zephyr, PlatformIO) — is a first-class citizen of the fleet:

- appears in the admin portal Devices table
- receives OTA updates from the same rollout pipeline
- flows into Grafana panels and the audit log
- auto-discoverable by any Home Assistant pointed at the same broker

Compliance with this contract is **mandatory** for any firmware intended to
ship to a patient site. Firmware that does not comply cannot be OTA-updated,
cannot be centrally monitored, and is effectively unmanaged — which is
disqualifying for hospital deployment.

---

# 1. Transport

| Item | Value |
|---|---|
| Broker host | `fleet-mqtt.homeadapt.us` |
| Port | `8883` (TLS) |
| Protocol | MQTT 3.1.1 (5.0 also accepted) |
| TLS | required; pin against the Cloudflare Origin CA PEM in `credentials/mqtt_credentials.txt` |
| Username / password | in `credentials/mqtt_credentials.txt` |
| Keepalive | 60 s recommended |
| Clean session | `true` |

Plaintext (port 1883) is not exposed.

# 2. Device identity

Every device MUST use a stable, globally unique `device_id` derived from its
WiFi MAC address:

```
DEVICE_ID = "esp32-" + lower(last_6_hex_of_wifi_mac, dashless)
```

Examples:
- MAC `1C:C3:AB:FA:48:D0` → `esp32-fa48d0`
- MAC `1C:C3:AB:FA:43:FC` → `esp32-fa43fc`

This matches ESPHome's `name_add_mac_suffix: true` convention. A fixed name
without the MAC suffix collides the moment you deploy two chips.

# 3. Topic layout

All topics are framed under `fleet/<DEVICE_ID>/`:

| Topic | Direction | QoS | Retain | Meaning |
|---|---|---|---|---|
| `fleet/<DEVICE_ID>/register` | pub | 1 | **false** | One-shot on boot |
| `fleet/<DEVICE_ID>/heartbeat` | pub | 0 | false | Every 30 s |
| `fleet/<DEVICE_ID>/ota/cmd` | sub | 0 | — | Admin-sent OTA trigger |
| `fleet/<DEVICE_ID>/ota/status` | pub | 0 | false | OTA progress / result |
| `fleet/<DEVICE_ID>/status` | pub | 0 | **true** | Online/offline availability (optional but recommended for HA) |
| `fleet/<DEVICE_ID>/log` | pub | 0 | false | Optional: forward device log lines; Loki ingests them |
| `fleet/<DEVICE_ID>/alert` | pub | 1 | false | Optional: one-shot critical alerts |

⚠️ `register` MUST NOT be retained. A retained register message replays into
the backend on every broker-side restart and silently overwrites any admin
edits to home_id / label / custom_id. We learned that the hard way.

# 4. Payload shapes

## 4.1 Register (one-shot on boot)

```json
{
  "mac": "1C:C3:AB:FA:48:D0",
  "version": "arduino-pir-1.0.0",
  "role": "arduino_pir",
  "home_id": "<from NVS; '' if not yet provisioned>",
  "label": "<from NVS>",
  "custom_id": "<from NVS>"
}
```

Required: `mac`, `version`, `role`. The three provisioning fields are required
keys; send empty strings if the device has never been through the captive
portal. They become populated once the homeowner fills the form.

## 4.2 Heartbeat (every 30 s)

```json
{
  "uptime": 123,
  "heap": 145000,
  "rssi": -55
}
```

Plus any sensor readings the firmware wants to report. The backend stores the
three base fields natively; extra fields are accepted and discoverable via
Grafana/Loki. Examples: `motion`, `temperature_c`, `humidity_pct`,
`battery_mv`.

## 4.3 OTA command (received)

```json
{
  "version": "arduino-pir-1.1.0",
  "url": "https://fleet-mqtt.homeadapt.us/firmware/arduino-pir-1.1.0/firmware.bin",
  "checksum": "<sha256 hex>"
}
```

On receipt:

1. Publish `{"status": "downloading", "version": "<version>"}` to
   `fleet/<id>/ota/status`.
2. Download the binary via HTTPS. Pin the CA PEM. `esp_https_ota_begin()` in
   ESP-IDF (Arduino: `HTTPUpdate` with `WiFiClientSecure`).
3. Publish `{"status": "flashing", ...}`.
4. Flash, verify.
5. If success: publish `{"status": "success", ...}` → pump the MQTT loop for
   a couple of seconds (don't reboot with the publish still in the queue) →
   `esp_restart()`.
6. If fail: publish `{"status": "failed", ...}` → do NOT reboot — the old
   firmware is still the last known good.

Reference implementation: `reference/mqtt_ota.h`. It uses raw ESP-IDF calls
(`esp_https_ota_begin`, `esp_https_ota_perform`, `esp_https_ota_finish`)
that work identically from Arduino — just replace the ESPHome logging
macros with Serial.printf and the namespace wrappers are cosmetic.

## 4.4 OTA status (published)

```json
{ "status": "success", "version": "arduino-pir-1.1.0" }
```

Valid status values: `downloading`, `flashing`, `success`, `failed`.

## 4.5 Availability (optional, for HA)

```
Topic:   fleet/<DEVICE_ID>/status
Retain:  true
Payload on connect: "online"
Last-will payload:  "offline"
```

Configure the MQTT client's last-will with topic `fleet/<id>/status`,
payload `"offline"`, retained. On successful connect, publish `"online"`
retained. This lets HA show the device as Unavailable when WiFi drops.

# 5. NVS / Preferences layout

All saved values go into a single namespace. Keys:

| Key | Type | Use |
|---|---|---|
| `home_id` | string (≤64 chars) | Groups devices in one patient home |
| `label` | string (≤64 chars) | Human-friendly display name |
| `custom_id` | string (≤64 chars) | Installer-chosen short code |

For Arduino / ESP-IDF:

```cpp
#include <Preferences.h>
Preferences prov;
prov.begin("prov", false);
String home_id   = prov.getString("home_id", "");
String label     = prov.getString("label", "");
String custom_id = prov.getString("custom_id", "");
prov.end();
```

**Important**: in our ESPHome firmware, `home_id` / `label` / `custom_id`
survive OTA updates because they're stored under a fixed preference hash
`0x484F4D45` — independent of any config-version hash that rotates on
YAML edits. In Arduino with `Preferences`, the namespace name is the key;
as long as you always use `"prov"`, the data survives.

WiFi SSID and password also go into NVS. Arduino's `WiFi` library persists
them automatically when you call `WiFi.begin(ssid, password)` with
`WiFi.persistent(true)`. Alternatively, save them in your own `Preferences`
namespace — either works.

# 6. Captive provisioning portal

On first boot (or after factory reset), when no saved WiFi credentials are
present, the firmware MUST:

1. Start a soft-AP with SSID `esp32-test-onboard`, password `12345678`
2. Run a DNS redirector on UDP port 53 that answers every A-record query
   with `192.168.4.1` (so iOS/Android auto-pop the captive browser)
3. Run an HTTP server on port 80 serving a form at `GET /`
4. The form has 5 fields: `ssid`, `psk`, `home_id`, `custom_id`, `label`
5. On `POST /save`:
   - Save wifi creds + all 5 NVS fields
   - Respond 200 with a short "Saved. Rebooting…" page
   - Defer `esp_restart()` by ~1.5 s so the HTTP response actually flushes

Reference implementation: `reference/provision_portal.h` plus
`reference/dns_server.{h,cpp}`. The DNS server is pure lwIP/ESP-IDF and
ports to Arduino with zero changes (the `socket::` wrappers just expand
to Berkeley sockets).

**Deviating from the SSID / password strings breaks the installer workflow.**
Installers use one printed PDF that names them explicitly.

# 7. Factory reset

GPIO0 (the BOOT button on every ESP32 dev board) held for **10 seconds**:

- Clear the `prov` Preferences namespace
- Clear WiFi credentials (`WiFi.disconnect(true, true)` on Arduino)
- Reboot

This gesture is documented in the installer PDF. Matching it means any
tetradapt-shipped device responds to the same "press-and-hold BOOT for 10 s"
recovery.

# 8. Role taxonomy

Pick a single lowercase role string in the register payload. Current roles:

| Role | What it means |
|---|---|
| `sensor` | Generic ESPHome heartbeat-only sensor (our current fleet) |
| `arduino_pir` | Arduino-compiled PIR motion sensor |
| `arduino_door` | (future) reed-switch door sensor |
| `arduino_bp_gateway` | (future) BLE blood-pressure-cuff gateway |

When you introduce a new role, document it here and tell the fleet admin —
the dashboard picker filters by role.

# 9. OTA version naming

To keep mixed-framework rollouts safe, firmware version strings are
namespaced:

| Firmware family | Format | Example |
|---|---|---|
| ESPHome fleet (existing) | `<major>.<minor>.<patch>` | `18.1.4` |
| Arduino PIR | `arduino-pir-<major>.<minor>.<patch>` | `arduino-pir-1.0.0` |
| Arduino door sensor | `arduino-door-<major>.<minor>.<patch>` | `arduino-door-1.0.0` |
| Future Arduino families | `arduino-<device>-<major>.<minor>.<patch>` | |

Admins eyeballing the Firmware versions list instantly know which binary
belongs to which device family. An admin cannot accidentally target
ESPHome devices with an Arduino build (and vice versa) if version strings
are namespaced AND rollouts target by role.

# 10. Home Assistant auto-discovery (optional, recommended)

On first boot after provisioning, publish ONE retained message per sensor
to the `homeassistant/<component>/<DEVICE_ID>/<sensor>/config` topic with
a payload following the
[HA MQTT discovery schema](https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery).
See `schemas/ha_discovery.example.json` for the motion-sensor example.

HA running on the same broker will then auto-create the device and its
entities with zero manual `configuration.yaml` editing.

# 11. Conformance smoke test (before production)

Before a new firmware ships:

1. Point the device at the production broker.
2. Verify it appears in the portal Devices table within 1 minute of boot
   with correct `home_id`, `label`, `custom_id`, `role`, `version`.
3. Verify the heartbeat frequency by watching the `last_seen` column
   advance every ~30 s.
4. Fire a test OTA from the portal (using a tiny no-op version bump):
   - OTA event goes through `pending → downloading → flashing → success`
   - Device re-registers with the new version
   - `home_id` / `label` / `custom_id` are preserved (no re-provisioning needed)
5. Hold BOOT 10 s. Verify the device returns to the `esp32-test-onboard`
   AP with all NVS wiped.
6. Re-provision via the captive portal. Verify all 5 form fields flow
   into the backend correctly.

If steps 1-6 pass, the firmware is contract-compliant.

# 12. Non-goals (what the contract does NOT require)

- No specific language or framework
- No specific logging format (beyond the optional `/log` topic)
- No specific sensor payload schema beyond the 3 base heartbeat fields
- No specific deep-sleep / power-management strategy
- No specific GPIO assignments
- No specific ESP32 variant (classic, S3, C3, C6 all work)

# Appendix A — credentials hygiene

The `credentials/mqtt_credentials.txt` file contains production credentials.

- Store it in a password manager
- Do not commit to any public repo
- Do not paste into Slack / email / ticket systems
- If you suspect it's been leaked, request a rotation — we'll rotate the
  MQTT password on the broker and invalidate the old one

# Appendix B — contact

Primary fleet admin: Karthikeyan Jeyabalan
Fleet portal: https://mdmfleetmanagment.homeadapt.us/
Backend source: github.com/karthi1975/mdmfleetmanagement
