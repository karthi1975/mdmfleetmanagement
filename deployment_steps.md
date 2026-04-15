# Step-by-Step: Multi-User ESP32 OTA Deployment

## Phase 1 — Cloud infrastructure (DigitalOcean)

1. **Create droplet** — Ubuntu 24.04, 2 vCPU / 4 GB RAM minimum, add SSH key.
2. **Point DNS** — `fleet.example.com` and `mqtt.example.com` A-records → droplet IP.
3. **Install Docker + Compose** — `curl -fsSL https://get.docker.com | sh`.
4. **Firewall** — `ufw allow 22,80,443,8883/tcp`; block everything else.
5. **Copy repo** — `rsync` the `MDM_ESP32` project to `/opt/mdm_esp32/`.
6. **Create `.env`** — copy `.env.example`, set strong `POSTGRES_PASSWORD`, `SECRET_KEY`, `GRAFANA_ADMIN_PASSWORD`, `ESPHOME_PASSWORD`.
7. **Start stack** — `docker compose up -d`.
8. **Add TLS** — Caddy or certbot in front of nginx; auto-renew Let's Encrypt for `fleet.example.com`.
9. **Run DB migrations** — `docker compose exec fleet-api alembic upgrade head`.

## Phase 2 — Fleet server APIs

10. **Device registration endpoint** — `POST /api/v1/devices/register` — accepts bootstrap token, returns device JWT.
11. **Device claim endpoint** — `POST /api/v1/devices/{id}/claim` — links device to authenticated user.
12. **Target version endpoint** — `GET /api/v1/devices/{id}/target` — returns assigned firmware version + signed URL.
13. **Status reporting endpoint** — `POST /api/v1/devices/{id}/status` — device reports current version, uptime, health.
14. **Firmware publish endpoint** — `POST /api/v1/firmware/publish` — registers a new compiled `.bin` version in Postgres.
15. **Rollout controller** — admin API to set per-user or per-group target version (canary, staged).

## Phase 3 — Firmware build pipeline

16. **Create base template** — `esphome/common/base.yaml` with Wi-Fi, API, OTA HTTP-pull, MQTT TLS blocks.
17. **Per-device YAML with substitutions** — one template, substitutions per device (device_id, user_id, sensor set).
18. **Build script** — `scripts/build_firmware.sh` → runs `docker compose run --rm esphome compile ...` → outputs versioned `.bin` to `data/firmware/{user_id}/{device_type}-{version}.bin`.
19. **Sign the binary** — sign `.bin` with project private key; publish SHA256 + signature to fleet-api.
20. **Bake public key into firmware** — so each device verifies signatures before flashing.

## Phase 4 — Provisioning (bench side, before shipping to user)

21. **Flash bootstrap firmware over USB** — ESPHome image with `captive_portal` + `improv` component, cloud URL, unique device ID, bootstrap token.
22. **Label the device** — sticker/QR with device ID.
23. **Pre-register in Postgres** — device row created in "unclaimed" state, bootstrap token valid.

## Phase 5 — User onboarding (at home)

24. **Plug device in** — boots to Wi-Fi AP mode, LED indicates provisioning.
25. **User connects phone** → captive portal → enters home SSID + password.
26. **Device joins Wi-Fi** → calls `register` endpoint → receives permanent JWT.
27. **User logs into web app** → enters device ID (or scans QR) → device is claimed to their account.
28. **Device starts normal loop** — polls `target` every N minutes, publishes telemetry via MQTT.

## Phase 6 — OTA update rollout

29. **Developer edits YAML** → commits → CI compiles new `.bin` → signs → publishes to fleet-api.
30. **Admin picks rollout** — e.g., 5% canary → one user → all users.
31. **Devices poll and see newer version** → download signed `.bin` from nginx over HTTPS.
32. **Device verifies signature + SHA256** → writes to inactive A/B partition → reboots.
33. **Boot success** → device reports new version → fleet-api marks successful.
34. **Boot failure** → bootloader auto-rolls back → fleet-api sees stale version → Grafana alert fires.

## Phase 7 — Observability & ops

35. **Grafana dashboards** — fleet health, version distribution, failed updates, per-user device status.
36. **Loki log aggregation** — device logs via MQTT → Loki → searchable per user/device.
37. **Alerting** — rollback rate > threshold, device offline > 24h, failed registrations.
38. **Backups** — nightly `pg_dump` + `data/firmware/` snapshot to DO Spaces.

## Phase 8 — Scale-out (when needed)

39. **Move Postgres to managed DB** — DigitalOcean Managed Postgres.
40. **Move firmware storage to Spaces** — CDN-backed `.bin` delivery.
41. **Horizontal scale fleet-api** — multiple replicas behind nginx load balancer.
42. **Mosquitto cluster** — or switch to EMQX for larger fleets.

**Order of execution for this sprint:** Phases 1 → 3 → 2 → 4 → 5 → 6 end-to-end with one real device and one test user, then harden security (TLS, signing, ACLs) before onboarding real users.
