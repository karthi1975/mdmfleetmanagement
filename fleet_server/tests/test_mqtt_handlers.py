"""Tests for MQTT message handlers — protocol-agnostic, real DB.

Handlers are tested directly with an AsyncSession (no MQTT broker needed).
This validates business logic in isolation from transport (DIP in action).
"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from fleet_server.models.device import Device
from fleet_server.models.ota_event import OTAEvent
from fleet_server.mqtt.handlers import handle_heartbeat, handle_ota_status, handle_registration
from fleet_server.tasks.scheduler import check_dead_devices


# ─── Registration Tests ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_register_new_device(db_session):
    device = await handle_registration(
        "esp32-new",
        json.dumps({"mac": "AA:BB:CC:DD:EE:FF", "version": "1.0.0", "role": "sensor"}),
        db_session,
    )
    assert device.device_id == "esp32-new"
    assert device.mac == "AA:BB:CC:DD:EE:FF"
    assert device.firmware_version == "1.0.0"
    assert device.status == "alive"


@pytest.mark.asyncio
async def test_register_existing_device_updates(db_session):
    # First registration
    await handle_registration(
        "esp32-re",
        json.dumps({"mac": "11:22:33:44:55:66", "version": "1.0.0", "role": "sensor"}),
        db_session,
    )
    # Re-register with new firmware
    device = await handle_registration(
        "esp32-re",
        json.dumps({"mac": "11:22:33:44:55:66", "version": "1.1.0", "role": "hub"}),
        db_session,
    )
    assert device.firmware_version == "1.1.0"
    assert device.role == "hub"
    assert device.status == "alive"

    # Verify only one device exists
    result = await db_session.execute(
        select(Device).where(Device.device_id == "esp32-re")
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_register_invalid_json(db_session):
    with pytest.raises(ValueError, match="Invalid registration payload"):
        await handle_registration("esp32-bad", "not-json", db_session)


# ─── Heartbeat Tests ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_updates_device(db_session):
    # Create device first
    await handle_registration(
        "esp32-hb",
        json.dumps({"mac": "AA:00:00:00:00:01", "version": "1.0.0"}),
        db_session,
    )
    # Send heartbeat
    updated = await handle_heartbeat(
        "esp32-hb",
        json.dumps({"uptime": 300, "heap": 45000, "rssi": -55}),
        db_session,
    )
    assert updated is True

    # Verify metrics stored
    result = await db_session.execute(
        select(Device).where(Device.device_id == "esp32-hb")
    )
    device = result.scalar_one()
    assert device.rssi == -55
    assert device.heap == 45000
    assert device.uptime == 300
    assert device.status == "alive"
    assert device.last_seen is not None


@pytest.mark.asyncio
async def test_heartbeat_unknown_device(db_session):
    updated = await handle_heartbeat(
        "ghost-device",
        json.dumps({"uptime": 10, "heap": 30000, "rssi": -70}),
        db_session,
    )
    assert updated is False


@pytest.mark.asyncio
async def test_heartbeat_invalid_json(db_session):
    result = await handle_heartbeat("esp32-x", "bad-json", db_session)
    assert result is False


@pytest.mark.asyncio
async def test_heartbeat_partial_payload(db_session):
    """Heartbeat with missing fields should still succeed."""
    await handle_registration(
        "esp32-partial",
        json.dumps({"mac": "AA:00:00:00:00:02", "version": "1.0.0"}),
        db_session,
    )
    updated = await handle_heartbeat(
        "esp32-partial",
        json.dumps({"uptime": 60}),
        db_session,
    )
    assert updated is True

    result = await db_session.execute(
        select(Device).where(Device.device_id == "esp32-partial")
    )
    device = result.scalar_one()
    assert device.uptime == 60
    assert device.rssi is None
    assert device.heap is None


# ─── Dead Device Detection Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_dead_device_detection(db_session):
    """Device with last_seen older than DEAD_THRESHOLD_SECONDS should be marked dead."""
    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    device = Device(
        device_id="esp32-dying",
        mac="DD:EE:AA:DD:00:01",
        firmware_version="1.0.0",
        status="alive",
        last_seen=old_time,
    )
    db_session.add(device)
    await db_session.commit()

    dead_ids = await check_dead_devices(db=db_session)
    assert "esp32-dying" in dead_ids

    # Verify status changed
    await db_session.refresh(device)
    assert device.status == "dead"


@pytest.mark.asyncio
async def test_alive_device_not_marked_dead(db_session):
    """Device with recent heartbeat should stay alive."""
    recent_time = datetime.now(timezone.utc) - timedelta(seconds=30)
    device = Device(
        device_id="esp32-healthy",
        mac="DD:EE:AA:DD:00:02",
        firmware_version="1.0.0",
        status="alive",
        last_seen=recent_time,
    )
    db_session.add(device)
    await db_session.commit()

    dead_ids = await check_dead_devices(db=db_session)
    assert "esp32-healthy" not in dead_ids

    await db_session.refresh(device)
    assert device.status == "alive"


@pytest.mark.asyncio
async def test_unknown_device_not_affected(db_session):
    """Devices with status 'unknown' should not be marked dead."""
    old_time = datetime.now(timezone.utc) - timedelta(seconds=200)
    device = Device(
        device_id="esp32-unknown",
        mac="DD:EE:AA:DD:00:03",
        firmware_version="1.0.0",
        status="unknown",
        last_seen=old_time,
    )
    db_session.add(device)
    await db_session.commit()

    dead_ids = await check_dead_devices(db=db_session)
    assert "esp32-unknown" not in dead_ids


@pytest.mark.asyncio
async def test_dead_detection_multiple_devices(db_session):
    """Multiple dead devices detected in one check."""
    old_time = datetime.now(timezone.utc) - timedelta(seconds=150)
    devices = [
        Device(device_id=f"esp32-dead-{i}", mac=f"DD:00:00:00:00:{i:02d}",
               firmware_version="1.0.0", status="alive", last_seen=old_time)
        for i in range(3)
    ]
    db_session.add_all(devices)
    await db_session.commit()

    dead_ids = await check_dead_devices(db=db_session)
    assert len(dead_ids) == 3


@pytest.mark.asyncio
async def test_revive_dead_device_via_heartbeat(db_session):
    """Dead device comes back alive on heartbeat."""
    old_time = datetime.now(timezone.utc) - timedelta(seconds=200)
    device = Device(
        device_id="esp32-revive",
        mac="DD:EE:AA:DD:00:04",
        firmware_version="1.0.0",
        status="alive",
        last_seen=old_time,
    )
    db_session.add(device)
    await db_session.commit()

    # Mark dead
    await check_dead_devices(db=db_session)
    await db_session.refresh(device)
    assert device.status == "dead"

    # Heartbeat revives
    await handle_heartbeat(
        "esp32-revive",
        json.dumps({"uptime": 5, "heap": 40000, "rssi": -40}),
        db_session,
    )
    await db_session.refresh(device)
    assert device.status == "alive"


# ─── OTA Status Handler Tests ──────────────────────────────────────

@pytest.mark.asyncio
async def test_ota_status_success_updates_event_and_firmware(db_session):
    """OTA success should update event status and device firmware version."""
    device = Device(
        device_id="esp32-ota-1", mac="OT:AA:00:00:00:01",
        firmware_version="1.0.0", status="alive",
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(device)
    event = OTAEvent(
        device_id="esp32-ota-1", from_version="1.0.0",
        to_version="2.0.0", status="pending",
    )
    db_session.add(event)
    await db_session.commit()

    result = await handle_ota_status(
        "esp32-ota-1",
        json.dumps({"status": "success", "version": "2.0.0"}),
        db_session,
    )
    assert result is True

    await db_session.refresh(event)
    assert event.status == "success"
    assert event.completed_at is not None

    await db_session.refresh(device)
    assert device.firmware_version == "2.0.0"


@pytest.mark.asyncio
async def test_ota_status_failed_updates_event(db_session):
    """OTA failure should update event status but not firmware version."""
    device = Device(
        device_id="esp32-ota-2", mac="OT:AA:00:00:00:02",
        firmware_version="1.0.0", status="alive",
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(device)
    event = OTAEvent(
        device_id="esp32-ota-2", from_version="1.0.0",
        to_version="2.0.0", status="downloading",
    )
    db_session.add(event)
    await db_session.commit()

    result = await handle_ota_status(
        "esp32-ota-2",
        json.dumps({"status": "failed", "version": "2.0.0"}),
        db_session,
    )
    assert result is True

    await db_session.refresh(event)
    assert event.status == "failed"
    assert event.completed_at is not None

    await db_session.refresh(device)
    assert device.firmware_version == "1.0.0"  # unchanged


@pytest.mark.asyncio
async def test_ota_status_downloading_updates_event(db_session):
    """Downloading status should update event but not complete it."""
    device = Device(
        device_id="esp32-ota-3", mac="OT:AA:00:00:00:03",
        firmware_version="1.0.0", status="alive",
        last_seen=datetime.now(timezone.utc),
    )
    db_session.add(device)
    event = OTAEvent(
        device_id="esp32-ota-3", from_version="1.0.0",
        to_version="2.0.0", status="pending",
    )
    db_session.add(event)
    await db_session.commit()

    result = await handle_ota_status(
        "esp32-ota-3",
        json.dumps({"status": "downloading", "version": "2.0.0"}),
        db_session,
    )
    assert result is True

    await db_session.refresh(event)
    assert event.status == "downloading"
    assert event.completed_at is None


@pytest.mark.asyncio
async def test_ota_status_no_matching_event(db_session):
    """No active OTA event should return False."""
    result = await handle_ota_status(
        "ghost-device",
        json.dumps({"status": "success", "version": "9.9.9"}),
        db_session,
    )
    assert result is False


@pytest.mark.asyncio
async def test_ota_status_invalid_json(db_session):
    result = await handle_ota_status("esp32-x", "bad-json", db_session)
    assert result is False


@pytest.mark.asyncio
async def test_ota_status_missing_fields(db_session):
    result = await handle_ota_status(
        "esp32-x",
        json.dumps({"status": "success"}),  # missing version
        db_session,
    )
    assert result is False
