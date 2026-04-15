import pytest


COMMUNITY_PAYLOAD = {
    "community_id": "nrh-test",
    "name": "NRH Test",
    "description": "Test community",
}


@pytest.mark.asyncio
async def test_list_communities_empty(client):
    resp = await client.get("/api/communities/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_community(client):
    resp = await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    assert resp.status_code == 201
    assert resp.json()["community_id"] == "nrh-test"
    assert resp.json()["name"] == "NRH Test"


@pytest.mark.asyncio
async def test_create_community_duplicate(client):
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    resp = await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_get_community(client):
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    resp = await client.get("/api/communities/nrh-test")
    assert resp.status_code == 200
    assert resp.json()["name"] == "NRH Test"


@pytest.mark.asyncio
async def test_get_community_not_found(client):
    resp = await client.get("/api/communities/ghost")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_community(client):
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    resp = await client.patch(
        "/api/communities/nrh-test", json={"name": "NRH Updated"}
    )
    assert resp.status_code == 200
    assert resp.json()["name"] == "NRH Updated"


@pytest.mark.asyncio
async def test_delete_community(client):
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    resp = await client.delete("/api/communities/nrh-test")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_list_community_homes(client):
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    await client.post(
        "/api/homes/",
        json={"home_id": "h1", "patient_name": "Patient 1"},
    )
    await client.post("/api/homes/h1/communities/nrh-test")

    resp = await client.get("/api/communities/nrh-test/homes")
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["home_id"] == "h1"


@pytest.mark.asyncio
async def test_list_community_homes_empty(client):
    await client.post("/api/communities/", json=COMMUNITY_PAYLOAD)
    resp = await client.get("/api/communities/nrh-test/homes")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_community_homes_not_found(client):
    resp = await client.get("/api/communities/ghost/homes")
    assert resp.status_code == 404
