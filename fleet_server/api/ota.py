"""OTA rollout API — start, preview (dry-run), list events, history, abort."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.api.auth import get_current_user
from fleet_server.database import get_db
from fleet_server.models.user import User
from fleet_server.schemas.ota import (
    OTACampaign,
    OTAEventResponse,
    OTARolloutCreate,
    OTARolloutPreview,
    OTARolloutResponse,
)
from fleet_server.services.audit import AuditService
from fleet_server.services.ota import OTAService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> OTAService:
    from fleet_server.mqtt.client import mqtt_client

    return OTAService(db, publish_fn=mqtt_client.publish)


def get_audit(db: AsyncSession = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.post("/rollout", response_model=OTARolloutResponse, status_code=201)
async def start_rollout(
    payload: OTARolloutCreate,
    service: OTAService = Depends(get_service),
    audit: AuditService = Depends(get_audit),
    user: User = Depends(get_current_user),
):
    try:
        events = await service.start_rollout(
            target_version=payload.target_version,
            strategy=payload.strategy,
            canary_count=payload.canary_count,
            target_devices=payload.target_devices,
            target_community=payload.target_community,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    audit.user_id = user.id if user else None
    await audit.log(
        "ota_start",
        "rollout",
        {
            "target_version": payload.target_version,
            "strategy": payload.strategy,
            "total_devices": len(events),
            "device_ids": [e.device_id for e in events],
        },
    )
    return OTARolloutResponse(
        target_version=payload.target_version,
        strategy=payload.strategy,
        total_devices=len(events),
        events=events,
    )


@router.post("/preview", response_model=OTARolloutPreview)
async def preview_rollout(
    payload: OTARolloutCreate,
    service: OTAService = Depends(get_service),
):
    """Dry-run a rollout — show the admin what would be hit, no writes."""
    try:
        return await service.preview_rollout(
            target_version=payload.target_version,
            strategy=payload.strategy,
            canary_count=payload.canary_count,
            target_devices=payload.target_devices,
            target_community=payload.target_community,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/events", response_model=list[OTAEventResponse])
async def list_events(
    target_version: str | None = None,
    service: OTAService = Depends(get_service),
):
    return await service.get_events(target_version=target_version)


@router.get("/campaigns", response_model=list[OTACampaign])
async def list_campaigns(
    limit: int = 20,
    service: OTAService = Depends(get_service),
):
    """Rollout history — events grouped by (to_version, 1-min bucket)."""
    return await service.get_campaigns(limit=limit)


@router.post("/rollout/{target_version}/abort")
async def abort_rollout(
    target_version: str,
    service: OTAService = Depends(get_service),
):
    count = await service.abort_rollout(target_version)
    return {"cancelled": count, "target_version": target_version}
