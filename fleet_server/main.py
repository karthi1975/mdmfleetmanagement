"""Fleet Management API — application entry point.

Wires together: middleware stack, routers, MQTT client, scheduler.
Middleware order matters (outermost first): RequestID → Logging → CORS → ErrorHandling.
"""

import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from fleet_server.config import settings
from fleet_server.database import async_session
from fleet_server.middleware.error_handler import register_error_handlers
from fleet_server.middleware.logging_middleware import LoggingMiddleware
from fleet_server.middleware.request_id import RequestIDMiddleware

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    from fleet_server.mqtt.client import mqtt_client
    from fleet_server.tasks.scheduler import scheduler

    logger.info("Fleet API starting up")

    try:
        await mqtt_client.start()
    except Exception:
        logger.warning("MQTT broker not available — running without MQTT")

    scheduler.start()
    logger.info("APScheduler started (dead device check every 60s)")

    yield

    logger.info("Fleet API shutting down")
    scheduler.shutdown(wait=False)
    await mqtt_client.stop()


app = FastAPI(
    title="SmartHome — Fleet Management API | Tetradapt LLC",
    description="ESP32 Fleet Management — device tracking, OTA updates, broadcast notifications",
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware stack (order: outermost → innermost)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handlers
register_error_handlers(app)

# API routes
from fleet_server.api.router import api_router  # noqa: E402

app.include_router(api_router, prefix="/api")

# Serve firmware binaries at /firmware/{version}/firmware.bin for ESP32 OTA downloads
firmware_dir = Path(settings.FIRMWARE_STORAGE_PATH)
firmware_dir.mkdir(parents=True, exist_ok=True)
app.mount("/firmware", StaticFiles(directory=str(firmware_dir)), name="firmware")

# Admin UI (static HTML — provisioning form + ESP Web Tools flasher)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount(
        "/admin", StaticFiles(directory=str(_static_dir), html=True), name="admin"
    )


@app.get("/health")
async def health():
    """Comprehensive health check — verifies all critical dependencies."""
    checks = {"version": "0.1.0"}

    # Database
    try:
        async with async_session() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # MQTT
    try:
        from fleet_server.mqtt.client import mqtt_client

        checks["mqtt"] = "connected" if mqtt_client._client else "disconnected"
    except Exception:
        checks["mqtt"] = "error"

    # FCM
    checks["fcm"] = "configured" if settings.FCM_PROJECT_ID else "not configured"

    # Overall
    all_ok = checks["database"] == "ok"
    checks["status"] = "ok" if all_ok else "degraded"

    return checks
