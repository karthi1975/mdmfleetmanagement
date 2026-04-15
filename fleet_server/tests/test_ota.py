"""OTA rollout tests — canary strategy, abort, event tracking."""

import pytest
from unittest.mock import AsyncMock

from fleet_server.models.device import Device
from fleet_server.models.firmware import FirmwareVersion
from fleet_server.services.ota import OTAService


async def _seed_devices_and_firmware(db, tmp_path):
    """Create firmware + devices for OTA tests."""
    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    from fleet_server.services.firmware import FirmwareService
    fw_service = FirmwareService(db)
    await fw_service.upload("2.0.0", b"new-firmware", "OTA test release")

    devices = [
        Device(device_id=f"esp32-ota-{i}", mac=f"OT:AA:00:00:00:{i:02d}",
               firmware_version="1.0.0", status="alive")
        for i in range(5)
    ]
    db.add_all(devices)
    await db.commit()
    return devices


@pytest.mark.asyncio
async def test_canary_rollout(db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    mock_publish = AsyncMock()
    service = OTAService(db_session, publish_fn=mock_publish)

    events = await service.start_rollout(
        target_version="2.0.0", strategy="canary", canary_count=2
    )

    assert len(events) == 2
    assert all(e.status == "pending" for e in events)
    assert all(e.to_version == "2.0.0" for e in events)
    assert all(e.from_version == "1.0.0" for e in events)
    assert mock_publish.call_count == 2

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_full_rollout(db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    mock_publish = AsyncMock()
    service = OTAService(db_session, publish_fn=mock_publish)

    events = await service.start_rollout(
        target_version="2.0.0", strategy="full"
    )

    assert len(events) == 5
    assert mock_publish.call_count == 5

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_rollout_skips_already_on_version(db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    # Update one device to target version
    d = await db_session.get(Device, "esp32-ota-0")
    d.firmware_version = "2.0.0"
    await db_session.commit()

    service = OTAService(db_session, publish_fn=AsyncMock())
    events = await service.start_rollout(
        target_version="2.0.0", strategy="full"
    )

    assert len(events) == 4  # One skipped
    device_ids = {e.device_id for e in events}
    assert "esp32-ota-0" not in device_ids

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_rollout_target_specific_devices(db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    service = OTAService(db_session, publish_fn=AsyncMock())

    events = await service.start_rollout(
        target_version="2.0.0",
        strategy="full",
        target_devices=["esp32-ota-1", "esp32-ota-3"],
    )

    assert len(events) == 2
    device_ids = {e.device_id for e in events}
    assert device_ids == {"esp32-ota-1", "esp32-ota-3"}

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_rollout_unknown_firmware(db_session):
    service = OTAService(db_session, publish_fn=AsyncMock())
    with pytest.raises(ValueError, match="not found"):
        await service.start_rollout(target_version="99.99.99")


@pytest.mark.asyncio
async def test_abort_rollout(db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    service = OTAService(db_session, publish_fn=AsyncMock())

    await service.start_rollout(target_version="2.0.0", strategy="full")
    cancelled = await service.abort_rollout("2.0.0")

    assert cancelled == 5

    events = await service.get_events(target_version="2.0.0")
    assert all(e.status == "cancelled" for e in events)

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_get_events(db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    service = OTAService(db_session, publish_fn=AsyncMock())

    await service.start_rollout(target_version="2.0.0", strategy="canary", canary_count=3)
    events = await service.get_events(target_version="2.0.0")
    assert len(events) == 3

    all_events = await service.get_events()
    assert len(all_events) == 3

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_rollout_without_publish(db_session, tmp_path):
    """Rollout works without publish function (offline mode)."""
    await _seed_devices_and_firmware(db_session, tmp_path)
    service = OTAService(db_session, publish_fn=None)

    events = await service.start_rollout(target_version="2.0.0", strategy="canary", canary_count=1)
    assert len(events) == 1

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_start_rollout(client, db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)

    resp = await client.post("/api/ota/rollout", json={
        "target_version": "2.0.0",
        "strategy": "canary",
        "canary_count": 2,
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["target_version"] == "2.0.0"
    assert data["total_devices"] == 2
    assert len(data["events"]) == 2

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_rollout_bad_version(client):
    resp = await client.post("/api/ota/rollout", json={
        "target_version": "nonexistent",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_abort_rollout(client, db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    await client.post("/api/ota/rollout", json={
        "target_version": "2.0.0", "strategy": "full",
    })

    resp = await client.post("/api/ota/rollout/2.0.0/abort")
    assert resp.status_code == 200
    assert resp.json()["cancelled"] == 5

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_list_events(client, db_session, tmp_path):
    await _seed_devices_and_firmware(db_session, tmp_path)
    await client.post("/api/ota/rollout", json={
        "target_version": "2.0.0", "strategy": "canary", "canary_count": 3,
    })

    resp = await client.get("/api/ota/events?target_version=2.0.0")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"
