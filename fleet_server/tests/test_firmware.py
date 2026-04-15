"""Firmware upload and listing tests."""

import pytest

from fleet_server.services.firmware import FirmwareService


@pytest.mark.asyncio
async def test_upload_firmware(db_session, tmp_path):
    service = FirmwareService(db_session)
    # Override storage path to tmp
    from fleet_server import config
    original = config.settings.FIRMWARE_STORAGE_PATH
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    fw = await service.upload("2.0.0", b"fake-firmware-binary", "Test release")

    assert fw.version == "2.0.0"
    assert fw.checksum  # SHA-256 present
    assert len(fw.checksum) == 64
    assert fw.release_notes == "Test release"

    # File exists on disk
    assert (tmp_path / "2.0.0" / "firmware.bin").exists()
    assert (tmp_path / "2.0.0" / "firmware.bin").read_bytes() == b"fake-firmware-binary"

    config.settings.FIRMWARE_STORAGE_PATH = original


@pytest.mark.asyncio
async def test_get_by_version(db_session, tmp_path):
    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    service = FirmwareService(db_session)
    await service.upload("3.0.0", b"binary", "v3")

    found = await service.get_by_version("3.0.0")
    assert found is not None
    assert found.version == "3.0.0"

    not_found = await service.get_by_version("99.0.0")
    assert not_found is None

    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_get_all_ordered(db_session, tmp_path):
    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    service = FirmwareService(db_session)
    await service.upload("1.0.0", b"v1", "first")
    await service.upload("1.1.0", b"v1.1", "second")

    all_fw = await service.get_all()
    assert len(all_fw) == 2
    assert all_fw[0].version == "1.1.0"  # newest first

    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_upload_firmware(client, db_session, tmp_path):
    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    resp = await client.post(
        "/api/firmware/",
        data={"version": "4.0.0", "release_notes": "API upload"},
        files={"file": ("firmware.bin", b"api-binary-content", "application/octet-stream")},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["version"] == "4.0.0"
    assert len(data["checksum"]) == 64

    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_upload_duplicate(client, db_session, tmp_path):
    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    await client.post(
        "/api/firmware/",
        data={"version": "5.0.0"},
        files={"file": ("fw.bin", b"binary", "application/octet-stream")},
    )
    resp = await client.post(
        "/api/firmware/",
        data={"version": "5.0.0"},
        files={"file": ("fw.bin", b"binary2", "application/octet-stream")},
    )
    assert resp.status_code == 409

    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_list_firmware(client, db_session, tmp_path):
    from fleet_server import config
    config.settings.FIRMWARE_STORAGE_PATH = str(tmp_path)

    await client.post(
        "/api/firmware/",
        data={"version": "6.0.0"},
        files={"file": ("fw.bin", b"bin", "application/octet-stream")},
    )
    resp = await client.get("/api/firmware/")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1

    config.settings.FIRMWARE_STORAGE_PATH = "./data/firmware"


@pytest.mark.asyncio
async def test_api_get_firmware_not_found(client):
    resp = await client.get("/api/firmware/99.99.99")
    assert resp.status_code == 404
