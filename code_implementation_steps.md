# ESP32 Fleet Management — Implementation Steps

> Implementation plan for local development. ESP32 hardware testing first, Home Assistant added later.

## Implementation Order

```
Phase 0 → 1 → 2 → 3 → [7: Flash ESP32 + E2E Test] → 4 → 5 → 6
```

Get to a working **ESP32 → MQTT → Fleet API → PostgreSQL** loop as fast as possible.

---

## Phase 0: Project Scaffolding

- [ ] `.gitignore` — Python, venv, .env, Docker, firmware, ESPHome secrets
- [ ] `.env.example` + `.env` — DB URLs (async + sync), MQTT, fleet config
- [ ] `requirements.txt` — fastapi, sqlalchemy[asyncio], asyncpg, aiomqtt, apscheduler, pytest
- [ ] `fleet_server/` directory tree with all `__init__.py` files
- [ ] `Dockerfile` — Python 3.13-slim, install deps, uvicorn
- [ ] `docker-compose.yml` — postgres (healthcheck), mosquitto, nginx, fleet-api
- [ ] `mosquitto/mosquitto.conf` — port 1883, anonymous for local dev
- [ ] `nginx/nginx.conf` — proxy /api/, serve /firmware/ static
- [ ] `data/` dirs — firmware/, broadcast/, backups/
- [ ] `pytest.ini` — asyncio_mode=auto

**Verify:** `pip install -r requirements.txt && docker compose up -d postgres mosquitto`

---

## Phase 1: Database & Models

- [ ] `fleet_server/models/base.py` — DeclarativeBase with naming convention
- [ ] `fleet_server/config.py` — Pydantic BaseSettings from .env
- [ ] `fleet_server/database.py` — async engine, session factory, get_db
- [ ] Models: `device.py`, `home.py`, `community.py`, `broadcast.py`, `firmware.py`, `ota_event.py`, `audit_log.py`
- [ ] `models/__init__.py` — import all models (Alembic needs this)
- [ ] Alembic init + configure env.py with sync URL
- [ ] `alembic revision --autogenerate -m "initial schema"`
- [ ] `fleet_server/scripts/seed.py` — communities (NRH, Kaiser, St Jude, Sutter), test homes + devices

**Verify:** `alembic upgrade head && python -m fleet_server.scripts.seed`

---

## Phase 2: Core API + Tests

- [ ] `fleet_server/main.py` — FastAPI app, lifespan, CORS, /health
- [ ] `fleet_server/api/router.py` — aggregated router
- [ ] Pydantic schemas: `device.py`, `home.py`, `community.py`
- [ ] API routes: `devices.py` (CRUD + filter), `homes.py` (CRUD + community assign), `communities.py` (CRUD + list homes)
- [ ] `tests/conftest.py` — test DB (fleet_test), override get_db, AsyncClient
- [ ] Tests: `test_devices.py`, `test_homes.py`, `test_communities.py`

**Verify:** `pytest -v` all green → `curl localhost:8000/docs` → OpenAPI UI

---

## Phase 3: MQTT Integration

- [ ] `fleet_server/mqtt/client.py` — MQTTManager singleton (connect, subscribe, dispatch)
- [ ] Update `main.py` lifespan — start MQTT listener + APScheduler
- [ ] `fleet_server/mqtt/heartbeat.py` — update device status/metrics on heartbeat
- [ ] `fleet_server/mqtt/registration.py` — auto-create/update device on register
- [ ] `fleet_server/tasks/scheduler.py` — AsyncIOScheduler, check_dead_devices (60s interval, 90s threshold)
- [ ] `tests/test_mqtt.py` — heartbeat, registration, dead detection tests

**Verify:**
```bash
mosquitto_pub -h localhost -t "fleet/esp32-test/register" \
  -m '{"mac":"AA:BB:CC:DD:EE:FF","version":"1.0.0","role":"sensor"}'
curl localhost:8000/api/devices/esp32-test  # → status: alive
```

---

## Phase 7: ESP32 + End-to-End Test (do this after Phase 3!)

- [ ] `esphome/common/base.yaml` — MQTT heartbeat, register on boot, OTA
- [ ] `esphome/devices/esp32-test.yaml` — first device using base template
- [ ] `esphome/secrets.yaml` — WiFi, MQTT broker (Mac IP), OTA password
- [ ] `pip install esphome` in venv
- [ ] `esphome run esphome/devices/esp32-test.yaml` — flash via USB

**End-to-End Flow (no Home Assistant needed):**
```
ESP32 (real hardware, USB flashed)
  → WiFi → your Mac's IP:1883
    → Mosquitto Docker (MQTT broker)
      → Fleet API (MQTT listener auto-creates device)
        → PostgreSQL (heartbeats stored every 30s)

Verify: curl localhost:8000/api/devices/  → shows ESP32 with live RSSI, heap, uptime
Unplug ESP32 → wait 90s → curl again → status: "dead"
Plug back in → status: "alive"
```

---

## Phase 4: Broadcast Service

- [ ] `schemas/broadcast.py` — BroadcastCreate (community_ids, message, type, priority, scheduled_at)
- [ ] `api/broadcast.py` — POST send, GET list, GET by id, GET acks
- [ ] `mqtt/broadcast.py` — publish to community MQTT topics
- [ ] Add broadcast ACK handler to MQTTManager
- [ ] Scheduled broadcasts via APScheduler one-shot jobs
- [ ] `tests/test_broadcast.py`

**Verify:** Send broadcast → `mosquitto_sub -t "fleet/broadcast/community/nrh"` receives it

---

## Phase 5: Firmware & OTA

- [ ] `schemas/firmware.py`, `schemas/ota.py`
- [ ] `api/firmware.py` — upload .bin (multipart), list, download
- [ ] `api/ota.py` — start rollout (canary/staged/full), advance, abort
- [ ] OTA status handler in MQTTManager
- [ ] `tests/test_firmware.py`, `tests/test_ota.py`

---

## Phase 6: Monitoring

- [ ] Add loki, grafana, rsyslog to docker-compose.yml
- [ ] `monitoring/loki-config.yml` — 7-day retention
- [ ] `monitoring/provisioning/datasources/loki.yml` — auto-provision
- [ ] `monitoring/provisioning/dashboards/json/fleet-overview.json` — pre-built dashboard
- [ ] `monitoring/rsyslog.conf` — forward to Loki

**Verify:** `open http://localhost:3000` → Grafana with Fleet dashboard

---

## File Count Summary

| Phase | Files | Cumulative |
|-------|-------|-----------|
| 0: Scaffolding | 12 | 12 |
| 1: Database | 16 | 28 |
| 2: Core API | 16 | 44 |
| 3: MQTT | 6 | 50 |
| 7: ESPHome | 5 | 55 |
| 4: Broadcast | 4 | 59 |
| 5: OTA | 6 | 65 |
| 6: Monitoring | 5 | 70 |
