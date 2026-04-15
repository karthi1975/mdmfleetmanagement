# ESP32 Fleet Management — Architecture Approach

## Overview

Central MDM (Mobile Device Management) system for ESP32 devices deployed across patient smart homes, integrated with Home Assistant. Three independent services:

1. **Fleet Management** — MQTT-based device tracking, heartbeat monitoring, OTA firmware updates
2. **Home Control** — ESPHome native API for local device control via Home Assistant
3. **Broadcast Messaging** — REST API + FCM push notifications to SmartHome iOS/Android apps by community group

---

## Requirement Mapping

| # | Requirement | Solution |
|---|-------------|----------|
| 1 | Report & display current fleet code levels | Fleet DB tracks firmware version per device. Dashboard + API. |
| 2 | Monitor fleet for alive/dead conditions | MQTT heartbeat every 30s. Dead after 90s silence. APScheduler detection. |
| 3 | Central logging (syslog) | ESP32 sends logs via UDP syslog → Rsyslog → Grafana Loki. |
| 4 | Perform remote updates for multiple devices | ESPHome OTA + custom orchestrator. Canary → staged → full rollout. |
| 5 | Qualys accessible | Fleet server API exposed for Qualys scanning. Devices behind VPN. |
| 6 | Broadcast messages to community groups | REST API → FCM push → SmartHome iOS/Android app. Per community (NRH, Kaiser, etc.). |

---

## Three Independent Services

```
┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ Service 1: Fleet Mgmt│  │ Service 2: Home Ctrl │  │ Service 3: Broadcast │
│ Protocol: MQTT :1883 │  │ Protocol: API :6053  │  │ Protocol: REST + FCM │
│ Client: ESP32 devices│  │ Client: ESP32 devices│  │ Client: Mobile app   │
│ Server: Fleet API    │  │ Server: Home Asst.   │  │ Server: Fleet API    │
│                      │  │                      │  │                      │
│ • Heartbeat (30s)    │  │ • Sensor data        │  │ • POST /api/broadcast│
│ • Auto-registration  │  │ • Device control     │  │ • FCM topic push     │
│ • OTA commands       │  │ • Automations        │  │ • Delivery ACK       │
│ • Dead detection     │  │ • ESPHome add-on     │  │ • Scheduled sends    │
│ • Firmware tracking  │  │ • Local only         │  │ • Community groups   │
└──────────────────────┘  └──────────────────────┘  └──────────────────────┘
```

---

## Fleet Server — Implemented Structure

```
fleet_server/                          # 63 files, 3,910 lines, 88 tests
├── main.py                            # FastAPI app, lifespan, middleware stack
├── config.py                          # Pydantic Settings (DB, MQTT, FCM, JWT)
├── database.py                        # Async SQLAlchemy engine + session
│
├── middleware/                         # Cross-cutting concerns
│   ├── request_id.py                  # Correlation ID on every request
│   ├── logging_middleware.py          # Structured JSON access logs
│   └── error_handler.py              # Global exception → consistent JSON errors
│
├── api/                               # Thin controllers (SRP)
│   ├── auth.py                        # JWT login, user CRUD, role guards
│   ├── devices.py                     # CRUD + audit logging
│   ├── homes.py                       # CRUD + community assignment
│   ├── communities.py                 # CRUD + home listing
│   ├── broadcast.py                   # FCM push (separate from MQTT)
│   ├── firmware.py                    # Upload + list
│   ├── ota.py                         # Canary/staged/full rollout
│   └── router.py                      # Aggregated APIRouter
│
├── services/                          # Business logic (DIP)
│   ├── auth.py                        # JWT issue/verify, bcrypt passwords
│   ├── audit.py                       # Compliance logging (HIPAA)
│   ├── broadcast.py                   # FCM push to community topics
│   ├── fcm.py                         # Firebase Cloud Messaging client
│   ├── firmware.py                    # Binary storage + checksum
│   └── ota.py                         # Rollout orchestration
│
├── repositories/                      # Generic CRUD (OCP)
│   ├── base.py                        # BaseRepository[T] — reusable CRUD
│   ├── device.py                      # + filtered queries
│   ├── home.py                        # + community assignment
│   └── community.py                   # + home listing
│
├── models/                            # SQLAlchemy ORM (10 tables)
│   ├── device.py                      # device_id, mac, firmware_version, status, rssi, heap
│   ├── home.py                        # home_id, patient_name, address
│   ├── community.py                   # community_id, name + home_community M2M
│   ├── broadcast.py                   # Broadcast + BroadcastAck
│   ├── firmware.py                    # FirmwareVersion (version, checksum, path)
│   ├── ota_event.py                   # OTAEvent (device, from/to version, status)
│   ├── audit_log.py                   # AuditLog (user, action, resource, details JSONB)
│   └── user.py                        # User (id, email, hashed_password, role)
│
├── schemas/                           # Pydantic v2 (ISP — separate Create/Update/Response)
│   ├── device.py, home.py, community.py, broadcast.py, firmware.py, ota.py
│
├── mqtt/                              # Fleet management only (NOT broadcast)
│   ├── client.py                      # aiomqtt transport — connect, subscribe, dispatch
│   └── handlers.py                    # Protocol-agnostic: heartbeat, registration
│
├── tasks/
│   └── scheduler.py                   # APScheduler: dead device check (60s interval)
│
└── tests/                             # 88 tests
    ├── test_auth.py                   # 12 tests — login, RBAC, token validation
    ├── test_devices.py                # 11 tests — CRUD, filter, audit
    ├── test_homes.py                  # 11 tests — CRUD, community assignment
    ├── test_communities.py            # 10 tests — CRUD, home listing
    ├── test_broadcast.py              # 14 tests — FCM push, schedule, delivery
    ├── test_firmware.py               # 7 tests — upload, checksum, list
    ├── test_ota.py                    # 12 tests — canary, abort, events
    └── test_mqtt_handlers.py          # 12 tests — heartbeat, register, dead detection
```

---

## Broadcast Service (FCM — Separate from MQTT)

Broadcast is a **standalone REST service** using Firebase Cloud Messaging for push delivery. It does NOT use MQTT.

**Flow:**
```
Admin → POST /api/broadcast → Fleet API → FCM HTTP v1 API → Firebase → iOS + Android apps
```

**How it works:**
1. Admin calls `POST /api/broadcast` with community IDs + message
2. Fleet API saves to PostgreSQL, calls FCM with topic = community_id
3. FCM pushes to all iOS/Android devices subscribed to that topic
4. Mobile app confirms receipt via `POST /api/broadcast/{id}/ack`
5. Dashboard shows delivery stats

**Community groups:** NRH, Kaiser, St Jude, Sutter Health, all

**FCM topic mapping:** community_id `nrh` → FCM topic `nrh`. App subscribes on login.

---

## Authentication & Authorization

JWT-based auth with role-based access control.

| Role | Access |
|------|--------|
| **admin** | Full access — CRUD, OTA, broadcast, user management, delete |
| **operator** | OTA rollouts, broadcast send, device/community management |
| **viewer** | Read-only — dashboard, fleet status, delivery reports |

**Endpoints:**
- `POST /api/auth/login` — email/password → JWT token
- `GET /api/auth/me` — current user info
- `POST /api/auth/users` — create user (admin only)

**Seeded users:** admin@tetradapt.com, operator@tetradapt.com, viewer@tetradapt.com

---

## Middleware Stack

Applied to every request (outermost → innermost):

| Middleware | Purpose |
|-----------|---------|
| RequestIDMiddleware | Adds `X-Request-ID` header, sets context var for correlation |
| LoggingMiddleware | Structured JSON access log (method, path, status, duration_ms) |
| CORSMiddleware | Cross-origin requests for dashboard |
| Error Handlers | IntegrityError → 409, OperationalError → 503, unhandled → 500 with request_id |

---

## MQTT Topics (Fleet Management Only)

```
fleet/{device}/heartbeat     # ESP32 → Server (every 30s)
fleet/{device}/register      # ESP32 → Server (on boot)
fleet/{device}/ota/cmd       # Server → ESP32 (firmware update command)
fleet/{device}/ota/status    # ESP32 → Server (OTA progress)
```

Broadcast does NOT use MQTT. It uses REST API + FCM.

---

## Home Assistant Integration

Each home's HA instance handles local device control only:
- ESPHome native API (:6053) for real-time sensor data and device control
- Automations for fall detection, emergency alerts
- ESPHome add-on for OTA from HA dashboard

HA does NOT handle broadcast messaging. That's the mobile app via FCM.

---

## Tech Stack

| Layer | Technology | Cost |
|-------|-----------|------|
| ESP32 firmware | ESPHome (YAML, ESP-IDF framework) | Free |
| Device-to-server | MQTT (Mosquitto) over TLS/WireGuard | Free (Docker) |
| Fleet server | FastAPI + APScheduler (Python 3.13) | Free |
| Database | PostgreSQL 16 (Docker) | Free |
| Auth | JWT (python-jose) + bcrypt | Free |
| Broadcast push | Firebase Cloud Messaging (FCM) | Free tier |
| Reverse proxy | Nginx (Docker) — SSL at Cloudflare | Free |
| DNS + SSL + CDN | Cloudflare (existing account) | Free |
| Logging | Rsyslog + Grafana Loki (Docker) | Free |
| Monitoring | Grafana OSS (Docker) | Free |
| VPN | WireGuard (Docker) | Free |
| Hosting (production) | DO Droplet 2 vCPU / 4GB | **$24/mo** |

---

## DigitalOcean Production Infrastructure

Single Droplet behind Cloudflare. All services in Docker Compose.

```
Internet → Cloudflare (DNS + SSL + CDN + DDoS) → DO Firewall
  → Droplet ($24/mo): Nginx, FastAPI, PostgreSQL, Mosquitto,
    WireGuard, Grafana, Loki, Rsyslog
  → WireGuard VPN → Patient Homes (HA + ESP32)
  → FCM → SmartHome Mobile Apps (broadcast)
```

**Cost:** $24/mo total. Cloudflare free. All services self-hosted.

---

## Implementation Status

| Phase | Status | Tests |
|-------|--------|-------|
| Scaffolding (Docker, configs) | Done | — |
| Database & Models (10 tables, Alembic) | Done | — |
| Core API (devices, homes, communities) | Done | 32 |
| MQTT Integration (heartbeat, register, dead detection) | Done | 12 |
| Broadcast Service (FCM push, ACK, scheduled) | Done | 14 |
| Firmware & OTA (upload, canary/staged/full) | Done | 19 |
| Auth System (JWT, RBAC, audit) | Done | 12 |
| Middleware (request ID, logging, errors) | Done | — |
| Monitoring (Grafana, Loki, Rsyslog) | Done | — |
| ESPHome Templates (base + test device) | Done | — |
| **Total** | **88 tests passing** | **88** |

---

## Open Decisions

1. **WireGuard vs Tailscale?** Tailscale is zero-config but adds dependency
2. **Firmware signing approach?** ESP-IDF secure boot vs application-level
3. **SmartHome mobile app technology?** Flutter vs React Native for FCM subscriber
4. **Message content restrictions?** Non-PHI only (clinic hours, wellness) or patient-specific?
