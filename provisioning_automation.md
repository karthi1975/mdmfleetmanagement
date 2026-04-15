# Automating Per-Device YAML — No More Copy-Paste

Manually editing YAML per device is a non-starter for a real fleet. Here's how we automate it end-to-end.

## The idea

Instead of humans editing files, a **"Provisioning" button in our admin UI** does everything: generate ID + token, render YAML from a template, compile firmware, download the `.bin`, and flash it — all in one click.

## The flow

```
Admin UI ──▶ Fleet API ──▶ Postgres ──▶ Template render ──▶ ESPHome compile ──▶ .bin download ──▶ Flash tool
```

### Step 1 — Admin clicks "Provision new device" in UI
A simple form: pick device type (room sensor, door lock, etc.), optionally assign to a user. That's it. No YAML touched.

### Step 2 — Fleet API generates identity automatically
```python
device_id = f"esp32-{secrets.token_hex(4)}"      # esp32-a1b2c3d4
device_token = secrets.token_urlsafe(32)          # long random
db.insert(device_id, device_token, device_type, status="unclaimed")
```

### Step 3 — API renders the YAML from a Jinja template
We keep **one** template per device type:

```yaml
# esphome/templates/room_sensor.yaml.j2
substitutions:
  device_id: "{{ device_id }}"
  device_token: "{{ device_token }}"
  fleet_url: "{{ fleet_url }}"

<<: !include ../common/base.yaml
# ...sensors, switches, etc...
```

The API fills in the variables and writes a temp file:
```python
rendered = template.render(device_id=..., device_token=..., fleet_url=...)
path = f"/tmp/provision/{device_id}.yaml"
Path(path).write_text(rendered)
```

### Step 4 — API triggers ESPHome compile in the already-running Docker service
```python
subprocess.run([
    "docker", "compose", "run", "--rm",
    "-v", "/tmp/provision:/config/provision",
    "esphome", "compile", f"provision/{device_id}.yaml"
])
```
The compiled `.bin` lands in `data/firmware/provision/{device_id}/`.

### Step 5 — UI offers two options
The API returns the `.bin` file to the UI. Admin can either:

**Option A — Download + flash locally**
Click "Download firmware" → get `.bin` → plug ESP32 into laptop → run `esptool.py write_flash 0x0 device.bin`. One command, no YAML editing.

**Option B — Browser flash via Web Serial (zero install)**
Use [ESP Web Tools](https://esphome.github.io/esp-web-tools/) — a JavaScript library that flashes ESP32s **directly from Chrome** over USB. Embed it in our admin UI:

```html
<esp-web-install-button manifest="/api/v1/devices/esp32-a1b2c3d4/manifest.json">
  <button>Plug in device and click here to flash</button>
</esp-web-install-button>
```

The manifest points at the freshly compiled `.bin`. Admin plugs in the ESP32, clicks the button, browser asks permission, flashes it. **Done in ~60 seconds, no tools installed, no YAML ever seen.**

### Step 6 — Print a label
After flashing, UI shows: device ID + QR code. Admin prints a sticker, slaps it on the device, ships it to the user.

## What the admin actually sees in the UI

```
┌─────────────────────────────────────┐
│  Provision New Device               │
├─────────────────────────────────────┤
│  Device type: [Room Sensor     ▼]   │
│  Assign to:   [user@example.com]    │
│                                     │
│           [ Generate & Build ]      │
│                                     │
│  ✓ ID created: esp32-a1b2c3d4       │
│  ✓ Firmware compiled (42s)          │
│                                     │
│  [ 🔌 Flash via browser ]           │
│  [ ⬇ Download .bin ]                │
│  [ 🖨 Print QR label ]              │
└─────────────────────────────────────┘
```

## What we need to build

| Piece | What it does | Effort |
|---|---|---|
| `esphome/templates/*.yaml.j2` | Jinja templates, one per device type | small |
| `POST /api/v1/devices/provision` | Generates ID/token, renders YAML, triggers compile, returns manifest URL | medium |
| `GET /api/v1/devices/{id}/firmware.bin` | Serves compiled binary | small |
| `GET /api/v1/devices/{id}/manifest.json` | ESP Web Tools manifest | small |
| Admin UI page | Form + ESP Web Tools button + QR generator | medium |
| Background job queue | Long compiles shouldn't block the HTTP request — push to Celery/RQ | medium |

## The payoff
- **Zero YAML editing** — templates are written once, reused forever.
- **Zero toolchain on admin's laptop** — everything runs on the droplet, flashing happens in the browser.
- **Consistent** — every device is provisioned the same way, no human error.
- **Auditable** — every provision event is a row in Postgres with timestamp, admin user, device ID.
- **Scales** — provisioning 1 device or 1,000 devices is the same workflow.

## The one-line summary
**We turn YAML editing into a form submission: admin clicks a button, the server generates a unique ID/token, renders a Jinja template, compiles the firmware in Docker, and the admin flashes the ESP32 directly from the browser using Web Serial — no files, no editors, no copy-paste.**
urrent status:                                                                                                                                                                             
  - Local fleet management server running end-to-end (fleet-api, postgres, mosquitto, nginx, esphome, grafana, loki) with one live ESP32 (esp32-test) on WiFi.                                
  - OTA pipeline fully autonomous — 6 successful over-the-air rollouts (5.0.0 → 10.0.0) via POST /api/ota/rollout, with server-side auto-reconciliation of device firmware version after      
  reboot.                                                                                                                                                                                     
                                                                                                                                                                                              
  Next steps:                                                                                                                                                                                 
  1. Scale to 2+ devices to validate canary/staged rollout strategies (only immediate single-device tested so far).                                                                           
  2. Migrate to DigitalOcean — deploy the stack (fleet-api, postgres, mosquitto, nginx) to a Droplet/App Platform, point a domain at it, and re-run the OTA round-trip from the cloud against 
  a LAN device to validate WAN connectivity and firmware download paths.                                                                                                                     
  3. Security hardening — signed firmware (private key on server, public key on device), HTTPS firmware downloads, MQTT TLS on 8883 with per-device tokens/ACLs.                              
  4. Observability — provision Grafana dashboards and alerts for offline devices, failed OTAs, and RSSI/heap trends (Loki + Grafana up but empty).              
  5. Fix device-side register publish so DB updates don't rely on the heartbeat auto-promote fallback.                                                                                        
  6. CI for firmware builds — auto-compile and upload on esphome/devices/*.yaml changes so version bumps are one commit, not manual docker commands.                                          
                                                                                                                                                 