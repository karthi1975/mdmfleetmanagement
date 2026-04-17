"""MQTT message handlers — protocol-agnostic, testable without a broker.

Each handler is a plain async function that takes parsed data + a db session.
They don't import aiomqtt — the transport layer (client.py) calls them.
This follows DIP: high-level handlers depend on abstractions (AsyncSession),
not on low-level MQTT transport details.
"""

import json
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.models.device import Device
from fleet_server.models.home import Home
from fleet_server.models.ota_event import OTAEvent

logger = logging.getLogger(__name__)


async def handle_heartbeat(device_name: str, raw_payload: str, db: AsyncSession) -> bool:
    """Process heartbeat — update device metrics and mark alive.

    Returns True if device was found and updated, False if unknown device.
    """
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.warning("Invalid heartbeat JSON from %s: %s", device_name, raw_payload)
        return False

    uptime = data.get("uptime")
    result = await db.execute(
        update(Device)
        .where(Device.device_id == device_name)
        .values(
            status="alive",
            last_seen=datetime.now(timezone.utc),
            rssi=data.get("rssi"),
            heap=data.get("heap"),
            uptime=uptime,
        )
        .returning(Device.device_id, Device.uptime)
    )
    row = result.first()
    await db.commit()

    if row is None:
        logger.warning("Heartbeat from unknown device: %s", device_name)
        return False

    # Auto-promote in-flight OTA when device reboots cleanly: a fresh-boot
    # heartbeat (low uptime) following an event in flashing/downloading is
    # treated as success. Devices don't always publish ota/status:success
    # because the reboot races MQTT flush.
    if uptime is not None and uptime < 180:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
        ota_result = await db.execute(
            select(OTAEvent)
            .where(
                OTAEvent.device_id == device_name,
                OTAEvent.status.in_(["pending", "downloading", "flashing"]),
                OTAEvent.started_at >= cutoff,
            )
            .order_by(OTAEvent.started_at.desc())
            .limit(1)
        )
        event = ota_result.scalar_one_or_none()
        if event is not None:
            event.status = "success"
            event.completed_at = datetime.now(timezone.utc)
            await db.execute(
                update(Device)
                .where(Device.device_id == device_name)
                .values(firmware_version=event.to_version)
            )
            await db.commit()
            logger.info(
                "Auto-promoted OTA %s -> %s (uptime=%ds post-reboot)",
                event.from_version, event.to_version, uptime,
            )

    logger.debug("Heartbeat processed for %s", device_name)
    return True


async def handle_registration(device_name: str, raw_payload: str, db: AsyncSession) -> Device:
    """Auto-register or update device on boot.

    Upsert pattern: create if new, update if existing.
    Returns the Device instance.
    """
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.warning("Invalid register JSON from %s: %s", device_name, raw_payload)
        raise ValueError(f"Invalid registration payload from {device_name}")

    mac = data.get("mac", "unknown")
    version = data.get("version", "unknown")
    role = data.get("role", "sensor")
    home_id = (data.get("home_id") or "").strip() or None
    display_name = (data.get("label") or "").strip() or None
    now = datetime.now(timezone.utc)

    # FK requires the home row to exist before the device references it.
    # If the installer typed a new home_id in the captive portal, auto-
    # create a placeholder home. An operator can fill in patient_name
    # and address from the admin console later.
    if home_id is not None:
        existing_home = await db.execute(
            select(Home).where(Home.home_id == home_id)
        )
        if existing_home.scalar_one_or_none() is None:
            db.add(Home(home_id=home_id, patient_name=home_id))
            await db.flush()
            logger.info("Auto-created home '%s' on device registration", home_id)

    result = await db.execute(
        select(Device).where(Device.device_id == device_name)
    )
    existing = result.scalar_one_or_none()

    if existing:
        existing.mac = mac
        existing.firmware_version = version
        existing.role = role
        existing.status = "alive"
        existing.last_seen = now
        if home_id is not None:
            existing.home_id = home_id
        if display_name is not None:
            existing.display_name = display_name
        await db.commit()
        await db.refresh(existing)
        logger.info(
            "Device re-registered: %s (v%s, home=%s, label=%s)",
            device_name, version, home_id, display_name,
        )
        return existing

    device = Device(
        device_id=device_name,
        mac=mac,
        firmware_version=version,
        role=role,
        status="alive",
        last_seen=now,
        home_id=home_id,
        display_name=display_name,
    )
    db.add(device)
    await db.commit()
    await db.refresh(device)
    logger.info(
        "New device registered: %s (v%s, role=%s, home=%s, label=%s)",
        device_name, version, role, home_id, display_name,
    )
    return device


async def handle_ota_status(device_name: str, raw_payload: str, db: AsyncSession) -> bool:
    """Process OTA status report from device — update OTAEvent and device firmware version.

    Expected payload: {"status": "downloading|flashing|success|failed", "version": "x.y.z"}
    Returns True if an OTA event was found and updated.
    """
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError:
        logger.warning("Invalid OTA status JSON from %s: %s", device_name, raw_payload)
        return False

    status = data.get("status")
    version = data.get("version")
    if not status or not version:
        logger.warning("OTA status missing fields from %s: %s", device_name, raw_payload)
        return False

    # Find the latest pending/in-progress OTA event for this device+version
    result = await db.execute(
        select(OTAEvent)
        .where(
            OTAEvent.device_id == device_name,
            OTAEvent.to_version == version,
            OTAEvent.status.in_(["pending", "downloading", "flashing"]),
        )
        .order_by(OTAEvent.started_at.desc())
        .limit(1)
    )
    event = result.scalar_one_or_none()

    if not event:
        logger.warning("No active OTA event for %s version %s", device_name, version)
        return False

    event.status = status
    if status in ("success", "failed"):
        event.completed_at = datetime.now(timezone.utc)

    # On success, update device firmware version
    if status == "success":
        await db.execute(
            update(Device)
            .where(Device.device_id == device_name)
            .values(firmware_version=version)
        )

    await db.commit()
    logger.info("OTA status for %s: %s (version %s)", device_name, status, version)
    return True
