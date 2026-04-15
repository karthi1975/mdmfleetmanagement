import pytest


HOME_PAYLOAD = {
    "home_id": "home-test-001",
    "patient_name": "Test Patient",
    "address": "123 Test St",
}

COMMUNITY_PAYLOAD = {
    "community_id": "test-community",
    "name": "Test Community",
    "description": "For testing",
}


@pytest.mark.asyncio
async def test_list_homes_empty(client):
    resp = await client.get("/api/homes/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_home(client):
    resp = await client.post("/api/homes/", json=HOME_PAYLOAD)
    assert resp.status_code == 201
    assert resp.json()["home_id"] == "home-test-001"
    assert resp.json()["patient_name"] == "Test Patient"


@pytest.mark.asyncio
async def test_create_home_duplicate(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    resp = await client.post("/api/homes/", json=HOME_PAYLOAD)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_home(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    resp = await client.get("/api/homes/home-test-001")
    assert resp.status_code == 200
    assert resp.json()["patient_name"] == "Test Patient"
    assert "communities" in resp.json()


@pytest.mark.asyncio
async def test_get_home_not_found(client):
    resp = await client.get("/api/homes/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_home(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    resp = await client.patch(
        "/api/homes/home-test-001", json={"patient_name": "Updated Name"}
    )
    assert resp.status_code == 200
    assert resp.json()["patient_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_home(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    resp = await client.delete("/api/homes/home-test-001")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_assign_community_to_home(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)

    resp = await client.post("/api/homes/home-test-001/communities/test-community")
    assert resp.status_code == 201

    resp = await client.get("/api/homes/home-test-001/communities")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["community_id"] == "test-community"


@pytest.mark.asyncio
async def test_remove_community_from_home(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    await client.post("/api/homes/home-test-001/communities/test-community")

    resp = await client.delete("/api/homes/home-test-001/communities/test-community")
    assert resp.status_code == 204

    resp = await client.get("/api/homes/home-test-001/communities")
    assert resp.json() == []


@pytest.mark.asyncio
async def test_assign_community_not_found(client):
    await client.post("/api/homes/", json=HOME_PAYLOAD)
    resp = await client.post("/api/homes/home-test-001/communities/ghost")
    assert resp.status_code == 404
