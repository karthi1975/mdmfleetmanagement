"""Scheduled OTA rollouts — queue a rollout to fire at a future time."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.api.auth import get_current_user, require_role
from fleet_server.database import get_db
from fleet_server.models.scheduled_rollout import ScheduledRollout
from fleet_server.models.user import User
from fleet_server.schemas.scheduled_rollout import (
    ScheduledRolloutCreate,
    ScheduledRolloutResponse,
)
from fleet_server.services.audit import AuditService

router = APIRouter()


def _audit(db: AsyncSession, user: User | None) -> AuditService:
    return AuditService(db, user_id=user.id if user else None)


@router.get("/", response_model=list[ScheduledRolloutResponse])
async def list_scheduled(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ScheduledRollout).order_by(ScheduledRollout.fire_at.asc())
    )
    return list(result.scalars().all())


@router.post(
    "/",
    response_model=ScheduledRolloutResponse,
    status_code=201,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def create_scheduled(
    payload: ScheduledRolloutCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Normalise to UTC — clients may send naive or local TZ.
    fire_at = payload.fire_at
    if fire_at.tzinfo is None:
        fire_at = fire_at.replace(tzinfo=timezone.utc)
    if fire_at < datetime.now(timezone.utc):
        raise HTTPException(400, "fire_at must be in the future")
    if not payload.target_devices:
        raise HTTPException(400, "target_devices must not be empty")

    row = ScheduledRollout(
        target_version=payload.target_version,
        strategy=payload.strategy,
        target_devices=payload.target_devices,
        canary_count=payload.canary_count,
        fire_at=fire_at,
        created_by=user.id if user else None,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    await _audit(db, user).log(
        "schedule",
        "rollout",
        {
            "id": row.id,
            "target_version": row.target_version,
            "fire_at": row.fire_at.isoformat(),
            "total_devices": len(row.target_devices),
        },
    )
    return row


@router.post(
    "/{scheduled_id}/cancel",
    response_model=ScheduledRolloutResponse,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def cancel_scheduled(
    scheduled_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = await db.get(ScheduledRollout, scheduled_id)
    if not row:
        raise HTTPException(404, "Not found")
    if row.status != "pending":
        raise HTTPException(409, f"Cannot cancel a rollout in status={row.status}")
    row.status = "cancelled"
    await db.commit()
    await db.refresh(row)
    await _audit(db, user).log(
        "cancel",
        "rollout",
        {"id": row.id, "target_version": row.target_version},
    )
    return row
