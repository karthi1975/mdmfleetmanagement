"""Broadcast API — push notifications via FCM to SmartHome mobile apps (SRP).

The FCM push function is injected from the FCM client singleton (DIP).
Broadcast is a separate REST service — does NOT use MQTT.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import get_db
from fleet_server.schemas.broadcast import (
    BroadcastAckCreate,
    BroadcastCreate,
    BroadcastDetailResponse,
    BroadcastResponse,
)
from fleet_server.services.broadcast import BroadcastService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> BroadcastService:
    """Inject BroadcastService with FCM push function (DIP)."""
    from fleet_server.services.fcm import fcm_client

    return BroadcastService(db, push_fn=fcm_client.push_to_topic)


@router.post("/", response_model=list[BroadcastResponse], status_code=201)
async def send_broadcast(
    payload: BroadcastCreate,
    service: BroadcastService = Depends(get_service),
):
    broadcasts = await service.send(
        community_ids=payload.community_ids,
        message=payload.message,
        msg_type=payload.type,
        priority=payload.priority,
        scheduled_at=payload.scheduled_at,
        sent_by=payload.sent_by,
    )
    if not broadcasts:
        raise HTTPException(
            status_code=400, detail="No valid communities found"
        )
    return broadcasts


@router.get("/", response_model=list[BroadcastResponse])
async def list_broadcasts(
    community_id: str | None = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    service: BroadcastService = Depends(get_service),
):
    return await service.get_all(
        community_id=community_id, skip=skip, limit=limit
    )


@router.get("/{broadcast_id}", response_model=BroadcastDetailResponse)
async def get_broadcast(
    broadcast_id: int,
    service: BroadcastService = Depends(get_service),
):
    broadcast = await service.get_by_id(broadcast_id)
    if not broadcast:
        raise HTTPException(status_code=404, detail="Broadcast not found")

    stats = await service.get_delivery_stats(broadcast_id)
    return BroadcastDetailResponse(
        **{c: getattr(broadcast, c) for c in BroadcastResponse.model_fields},
        acks=stats.get("acks", []),
        total_targets=stats.get("total_targets", 0),
        delivered_count=stats.get("delivered_count", 0),
    )


@router.post("/{broadcast_id}/ack", status_code=201)
async def acknowledge_broadcast(
    broadcast_id: int,
    payload: BroadcastAckCreate,
    service: BroadcastService = Depends(get_service),
):
    """Mobile app calls this to confirm receipt of broadcast notification."""
    ack = await service.record_ack(
        broadcast_id,
        home_id=str(payload.msg_id),
        status=payload.status,
        received_at=payload.received_at,
    )
    if not ack:
        raise HTTPException(status_code=404, detail="Broadcast not found")
    return {"status": "acknowledged"}
