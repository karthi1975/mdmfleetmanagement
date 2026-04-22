% Fleet Integration Kit — ESP32 Firmware Developer Handoff
% tetradapt HomeAdapt
% v1.0 · 2026-04-21

Everything you need to write an ESP32 firmware (Arduino, ESP-IDF, PlatformIO, or
anything else that compiles for ESP32) that plugs into the existing
HomeAdapt fleet management system.

Read **CONTRACT.md** first — it's the authoritative spec. Then open
`schemas/` for payload shapes, `reference/` for a working implementation
you can adapt, and `credentials/` for broker access.

---

# What this kit gives you

| File | Purpose |
|---|---|
| **CONTRACT.md** | Authoritative protocol specification. Read first. |
| `credentials/mqtt_credentials.txt` | Broker URL, username, password, CA PEM. Production creds — treat as secret. |
| `reference/mqtt_ota.h` | Full OTA handler — download + flash + publish status. Pure ESP-IDF. Copy-adapt. |
| `reference/provision_portal.h` | Captive-portal HTTP form. 5 fields. NVS save. Copy-adapt. |
| `reference/dns_server.h` + `.cpp` | Wildcard DNS redirector so iOS/Android auto-pop the portal browser. Pure lwIP. |
| `schemas/register.example.json` | What to publish on boot. |
| `schemas/heartbeat.example.json` | What to publish every 30 s. |
| `schemas/ota_cmd.example.json` | What you'll receive when admin starts a rollout. |
| `schemas/ota_status.example.json` | What to publish as the OTA progresses. |
| `schemas/ha_discovery.example.json` | Optional: auto-register your sensor in Home Assistant. |

---

# The six obligations

To be a full citizen of the fleet, your firmware must do all six. Skip
any one and the specific feature (monitoring, OTA, provisioning, etc.)
that obligation backs fails.

1. **Connect to the broker** over TLS. Use the CA PEM in
   `credentials/mqtt_credentials.txt`. See `CONTRACT.md §1`.

2. **Derive DEVICE_ID from MAC.** Last 6 hex digits, lowercase, dashless,
   prefixed with `esp32-`. See `CONTRACT.md §2`.

3. **Publish a register payload once on boot** to
   `fleet/<DEVICE_ID>/register`. Non-retained. QoS 1. See
   `schemas/register.example.json` and `CONTRACT.md §3, §4.1`.

4. **Publish a heartbeat every 30 s** to `fleet/<DEVICE_ID>/heartbeat`.
   Non-retained. QoS 0. Payload includes `uptime`, `heap`, `rssi` and
   any sensor readings. See `schemas/heartbeat.example.json` and
   `CONTRACT.md §4.2`.

5. **Subscribe to `fleet/<DEVICE_ID>/ota/cmd`**. On receipt: download the
   `url`, flash via `esp_https_ota` (pin the CA), publish status, reboot
   on success. See `reference/mqtt_ota.h` and `CONTRACT.md §4.3`.

6. **Run the provisioning portal** when WiFi creds are missing. SoftAP
   `esp32-test-onboard` / password `12345678`. Captive DNS + HTTP form
   at `192.168.4.1/`. 5 fields → NVS + WiFi save + reboot. See
   `reference/provision_portal.h` + `reference/dns_server.{h,cpp}`
   and `CONTRACT.md §6`.

Plus strongly recommended:

7. **Factory reset** — GPIO0 held 10 s wipes NVS + reboots. See
   `CONTRACT.md §7`.

8. **Availability last-will** — publish retained `"online"` to
   `fleet/<DEVICE_ID>/status` on connect, with a last-will `"offline"`
   retained. Makes the dashboard and Home Assistant show correct state
   when WiFi drops. See `CONTRACT.md §4.5`.

---

# Suggested implementation order

Working incrementally so you can verify each layer before moving on:

| Step | Do this | Verify |
|---|---|---|
| 1 | Hardcode your WiFi creds; connect over TLS; publish a register payload once | Device appears in the portal Devices table within 1 min. `role`, `version`, `mac` populated. |
| 2 | Add 30-s heartbeat loop | `last_seen` column in the dashboard advances every 30 s; status stays `alive`. |
| 3 | Subscribe to `ota/cmd`; copy the body of `reference/mqtt_ota.h` into your code | Admin does a test rollout; your device flashes the new binary and re-registers with new version. |
| 4 | Remove hardcoded WiFi; port `reference/provision_portal.h` + `dns_server.*` | Factory-reset the chip → joins `esp32-test-onboard` AP → form at `192.168.4.1/` shows 5 fields → save → device reconnects. |
| 5 | Wire your sensor (PIR, DHT22, whatever) | Heartbeat includes the new field; Grafana picks it up. |
| 6 | Add HA discovery publish (one retained message per sensor) | Home Assistant auto-adds the device card and entity with zero manual config. |

Total: 1-2 engineer-days if working from Arduino without prior ESP32 MQTT
experience; half a day for someone who's shipped an MQTT device before.

---

# Conformance smoke test

Before merging your firmware into production, run through `CONTRACT.md §11`:

1. ✅ Register arrives within 1 min of boot
2. ✅ Heartbeat every 30 s (`last_seen` advances)
3. ✅ Test OTA succeeds; new version shows in dashboard
4. ✅ `home_id` / `label` / `custom_id` survive OTA
5. ✅ Factory reset returns device to AP mode
6. ✅ Re-provisioning populates all 5 fields correctly

Check all six and you're clear to ship.

---

# Getting help

- Contract questions → CONTRACT.md answers most of them
- Reference code doesn't build → dependencies are pure ESP-IDF + lwIP; no
  ESPHome runtime needed. If something references `esphome::`, strip the
  namespace.
- Can't reach the broker → check the CA PEM is pinned correctly
  (`WiFiClientSecure::setCACert(...)`) and port 8883 is accessible from
  your dev network
- Dashboard doesn't show the device after register → check MQTT topic
  capitalization (all lowercase), no trailing slash, `device_id` matches
  your topic exactly

Primary contact: Karthikeyan Jeyabalan.
Portal: https://mdmfleetmanagment.homeadapt.us/
