from fastapi import APIRouter

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

api_router = APIRouter()

# Auth — public (login) + admin-only (user create)
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])

# Fleet resources — protected by role guards in each route
api_router.include_router(devices.router, prefix="/devices", tags=["devices"])
api_router.include_router(homes.router, prefix="/homes", tags=["homes"])
api_router.include_router(
    communities.router, prefix="/communities", tags=["communities"]
)

# Broadcast — separate REST service (FCM push)
api_router.include_router(
    broadcast.router, prefix="/broadcast", tags=["broadcast"]
)

# Firmware & OTA
api_router.include_router(firmware.router, prefix="/firmware", tags=["firmware"])
api_router.include_router(ota.router, prefix="/ota", tags=["ota"])
api_router.include_router(
    provisioning.router, prefix="/provisioning", tags=["provisioning"]
)
