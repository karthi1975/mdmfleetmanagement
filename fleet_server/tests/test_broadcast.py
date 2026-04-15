"""Broadcast tests — service + API + MQTT ACK handler.

BroadcastService is tested with a mock publish function (DIP),
verifying business logic without a real MQTT broker.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from fleet_server.models.community import Community, home_community
from fleet_server.models.home import Home
from fleet_server.services.broadcast import BroadcastService


# ─── Fixtures ───────────────────────────────────────────────────────

async def _seed_community_and_home(db):
    """Seed a community with one home for broadcast tests."""
    community = Community(
        community_id="nrh-test",
        name="NRH Test",
        description="Test community",
    )
    home = Home(home_id="home-test-001", patient_name="Patient A")
    db.add_all([community, home])
    await db.flush()
    await db.execute(
        home_community.insert().values(home_id="home-test-001", community_id="nrh-test")
    )
    await db.commit()
    return community, home


# ─── BroadcastService Unit Tests ────────────────────────────────────

@pytest.mark.asyncio
async def test_send_immediate_broadcast(db_session):
    await _seed_community_and_home(db_session)
    mock_push = AsyncMock(return_value=True)
    service = BroadcastService(db_session, push_fn=mock_push)

    broadcasts = await service.send(
        community_ids=["nrh-test"],
        message="Flu clinic Saturday 9am",
        msg_type="alert",
        priority="normal",
        sent_by="admin",
    )

    assert len(broadcasts) == 1
    assert broadcasts[0].community_id == "nrh-test"
    assert broadcasts[0].sent_at is not None
    assert broadcasts[0].message == "Flu clinic Saturday 9am"

    # Verify FCM push was called with (topic, title, body, priority)
    mock_push.assert_called_once()
    args = mock_push.call_args[0]
    assert args[0] == "nrh-test"         # FCM topic = community_id
    assert args[1] == "NRH Test"         # title = community name
    assert args[2] == "Flu clinic Saturday 9am"  # body = message
    assert args[3] == "normal"           # priority


@pytest.mark.asyncio
async def test_send_to_multiple_communities(db_session):
    await _seed_community_and_home(db_session)
    c2 = Community(community_id="kaiser-test", name="Kaiser Test")
    db_session.add(c2)
    await db_session.commit()

    mock_push = AsyncMock(return_value=True)
    service = BroadcastService(db_session, push_fn=mock_push)

    broadcasts = await service.send(
        community_ids=["nrh-test", "kaiser-test"],
        message="General announcement",
    )

    assert len(broadcasts) == 2
    assert mock_push.call_count == 2
    community_ids = {b.community_id for b in broadcasts}
    assert community_ids == {"nrh-test", "kaiser-test"}


@pytest.mark.asyncio
async def test_send_scheduled_broadcast(db_session):
    await _seed_community_and_home(db_session)
    mock_push = AsyncMock(return_value=True)
    service = BroadcastService(db_session, push_fn=mock_push)

    future_time = datetime(2030, 1, 1, tzinfo=timezone.utc)
    broadcasts = await service.send(
        community_ids=["nrh-test"],
        message="Scheduled message",
        scheduled_at=future_time,
    )

    assert len(broadcasts) == 1
    assert broadcasts[0].scheduled_at == future_time
    assert broadcasts[0].sent_at is None
    # Should NOT publish — it's scheduled for later
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_send_to_unknown_community(db_session):
    mock_push = AsyncMock(return_value=True)
    service = BroadcastService(db_session, push_fn=mock_push)

    broadcasts = await service.send(
        community_ids=["ghost-community"],
        message="Hello?",
    )

    assert len(broadcasts) == 0
    mock_push.assert_not_called()


@pytest.mark.asyncio
async def test_send_without_publish_fn(db_session):
    """Service works without publish — for testing/offline mode."""
    await _seed_community_and_home(db_session)
    service = BroadcastService(db_session, push_fn=None)

    broadcasts = await service.send(
        community_ids=["nrh-test"],
        message="No MQTT",
    )

    assert len(broadcasts) == 1
    assert broadcasts[0].sent_at is not None


@pytest.mark.asyncio
async def test_record_ack(db_session):
    await _seed_community_and_home(db_session)
    service = BroadcastService(db_session)

    broadcasts = await service.send(
        community_ids=["nrh-test"], message="Test ACK"
    )
    broadcast_id = broadcasts[0].id

    ack = await service.record_ack(
        broadcast_id, "home-test-001", "delivered"
    )
    assert ack is not None
    assert ack.broadcast_id == broadcast_id
    assert ack.home_id == "home-test-001"
    assert ack.status == "delivered"


@pytest.mark.asyncio
async def test_record_ack_unknown_broadcast(db_session):
    service = BroadcastService(db_session)
    ack = await service.record_ack(99999, "home-test-001", "delivered")
    assert ack is None


@pytest.mark.asyncio
async def test_delivery_stats(db_session):
    await _seed_community_and_home(db_session)
    service = BroadcastService(db_session)

    broadcasts = await service.send(
        community_ids=["nrh-test"], message="Stats test"
    )
    bid = broadcasts[0].id

    await service.record_ack(bid, "home-test-001", "delivered")
    stats = await service.get_delivery_stats(bid)

    assert stats["total_targets"] == 1
    assert stats["delivered_count"] == 1


@pytest.mark.asyncio
async def test_get_all_filter_by_community(db_session):
    await _seed_community_and_home(db_session)
    c2 = Community(community_id="other", name="Other")
    db_session.add(c2)
    await db_session.commit()

    service = BroadcastService(db_session)
    await service.send(community_ids=["nrh-test"], message="NRH msg")
    await service.send(community_ids=["other"], message="Other msg")

    nrh_only = await service.get_all(community_id="nrh-test")
    assert len(nrh_only) == 1
    assert nrh_only[0].community_id == "nrh-test"

    all_broadcasts = await service.get_all()
    assert len(all_broadcasts) == 2


# ─── API Integration Tests ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_send_broadcast(client, db_session):
    await _seed_community_and_home(db_session)

    resp = await client.post("/api/broadcast/", json={
        "community_ids": ["nrh-test"],
        "message": "API broadcast test",
        "type": "notification",
        "priority": "normal",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert len(data) == 1
    assert data[0]["community_id"] == "nrh-test"
    assert data[0]["message"] == "API broadcast test"


@pytest.mark.asyncio
async def test_api_send_broadcast_no_valid_community(client):
    resp = await client.post("/api/broadcast/", json={
        "community_ids": ["ghost"],
        "message": "Hello?",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_list_broadcasts(client, db_session):
    await _seed_community_and_home(db_session)
    await client.post("/api/broadcast/", json={
        "community_ids": ["nrh-test"],
        "message": "List test 1",
    })
    await client.post("/api/broadcast/", json={
        "community_ids": ["nrh-test"],
        "message": "List test 2",
    })

    resp = await client.get("/api/broadcast/")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_api_get_broadcast_detail(client, db_session):
    await _seed_community_and_home(db_session)
    create_resp = await client.post("/api/broadcast/", json={
        "community_ids": ["nrh-test"],
        "message": "Detail test",
    })
    bid = create_resp.json()[0]["id"]

    resp = await client.get(f"/api/broadcast/{bid}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "Detail test"
    assert data["total_targets"] == 1
    assert data["delivered_count"] == 0


@pytest.mark.asyncio
async def test_api_get_broadcast_not_found(client):
    resp = await client.get("/api/broadcast/99999")
    assert resp.status_code == 404
