from fastapi import APIRouter, Depends

from fleet_server.api import (
    auth,
    broadcast,
    communities,
    devices,
    firmware,
    homes,
    ota,
    provisioning,
)
from fleet_server.api.auth import require_role

api_router = APIRouter()

# Public: login + /me (routes inside auth.router apply their own guards).
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# All other resource routers require at least a valid JWT (any role).
# Tighter role checks (e.g. admin-only mutations) are applied per-route.
_any_auth = [Depends(require_role("admin", "operator", "viewer"))]

api_router.include_router(
    devices.router, prefix="/devices", tags=["devices"], dependencies=_any_auth
)
api_router.include_router(
    homes.router, prefix="/homes", tags=["homes"], dependencies=_any_auth
)
api_router.include_router(
    communities.router,
    prefix="/communities",
    tags=["communities"],
    dependencies=_any_auth,
)
api_router.include_router(
    broadcast.router, prefix="/broadcast", tags=["broadcast"], dependencies=_any_auth
)
api_router.include_router(
    firmware.router, prefix="/firmware", tags=["firmware"], dependencies=_any_auth
)
api_router.include_router(
    ota.router, prefix="/ota", tags=["ota"], dependencies=_any_auth
)

# Provisioning mixes public (ESP Web Tools manifest + firmware download)
# and authenticated (/provision, /jobs) endpoints. Guards live per-route.
api_router.include_router(
    provisioning.router, prefix="/provisioning", tags=["provisioning"]
)
