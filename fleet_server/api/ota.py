"""OTA rollout API — start, list events, abort."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import get_db
from fleet_server.schemas.ota import OTAEventResponse, OTARolloutCreate, OTARolloutResponse
from fleet_server.services.ota import OTAService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> OTAService:
    from fleet_server.mqtt.client import mqtt_client

    return OTAService(db, publish_fn=mqtt_client.publish)


@router.post("/rollout", response_model=OTARolloutResponse, status_code=201)
async def start_rollout(
    payload: OTARolloutCreate,
    service: OTAService = Depends(get_service),
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

    return OTARolloutResponse(
        target_version=payload.target_version,
        strategy=payload.strategy,
        total_devices=len(events),
        events=events,
    )


@router.get("/events", response_model=list[OTAEventResponse])
async def list_events(
    target_version: str | None = None,
    service: OTAService = Depends(get_service),
):
    return await service.get_events(target_version=target_version)


@router.post("/rollout/{target_version}/abort")
async def abort_rollout(
    target_version: str,
    service: OTAService = Depends(get_service),
):
    count = await service.abort_rollout(target_version)
    return {"cancelled": count, "target_version": target_version}
