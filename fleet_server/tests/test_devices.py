import pytest


DEVICE_PAYLOAD = {
    "device_id": "esp32-test-001",
    "mac": "AA:BB:CC:DD:EE:01",
    "firmware_version": "1.0.0",
    "role": "sensor",
}


@pytest.mark.asyncio
async def test_list_devices_empty(client):
    resp = await client.get("/api/devices/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_device(client):
    resp = await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    assert resp.status_code == 201
    data = resp.json()
    assert data["device_id"] == "esp32-test-001"
    assert data["status"] == "unknown"
    assert data["mac"] == "AA:BB:CC:DD:EE:01"


@pytest.mark.asyncio
async def test_create_device_duplicate(client):
    await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    resp = await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_device(client):
    await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    resp = await client.get("/api/devices/esp32-test-001")
    assert resp.status_code == 200
    assert resp.json()["device_id"] == "esp32-test-001"


@pytest.mark.asyncio
async def test_get_device_not_found(client):
    resp = await client.get("/api/devices/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_device(client):
    await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    resp = await client.patch(
        "/api/devices/esp32-test-001", json={"status": "alive"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "alive"


@pytest.mark.asyncio
async def test_update_device_not_found(client):
    resp = await client.patch("/api/devices/ghost", json={"status": "alive"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_device(client):
    await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    resp = await client.delete("/api/devices/esp32-test-001")
    assert resp.status_code == 204
    resp = await client.get("/api/devices/esp32-test-001")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_device_not_found(client):
    resp = await client.delete("/api/devices/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_filter_devices_by_status(client):
    await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    await client.post(
        "/api/devices/",
        json={**DEVICE_PAYLOAD, "device_id": "esp32-test-002", "mac": "AA:BB:CC:DD:EE:02"},
    )
    await client.patch("/api/devices/esp32-test-001", json={"status": "alive"})

    resp = await client.get("/api/devices/?status=alive")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["device_id"] == "esp32-test-001"


@pytest.mark.asyncio
async def test_filter_devices_by_role(client):
    await client.post("/api/devices/", json=DEVICE_PAYLOAD)
    await client.post(
        "/api/devices/",
        json={
            **DEVICE_PAYLOAD,
            "device_id": "esp32-hub-001",
            "mac": "AA:BB:CC:DD:EE:99",
            "role": "hub",
        },
    )
    resp = await client.get("/api/devices/?role=hub")
    assert len(resp.json()) == 1
