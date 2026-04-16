#!/usr/bin/env bash
# Nightly pg_dump of fleet_db. Keeps last 14 days.
set -euo pipefail
cd "$(dirname "$0")/.."
ts=$(date -u +%Y%m%d-%H%M)
out="data/backups/fleet_db-${ts}.sql.gz"
docker compose exec -T postgres pg_dump -U fleet -d fleet_db | gzip > "$out"
# prune anything older than 14 days
find data/backups -name "fleet_db-*.sql.gz" -mtime +14 -delete
echo "[backup] wrote $out ($(stat -c %s "$out") bytes)"
