"""Device group CRUD.

Device groups are static named lists of device_ids. When admin selects
"load group X" in the picker, the stored device_ids are copied into the
active selection. Groups survive device churn — a device_id removed
from the fleet cascades its membership row away but the group row stays.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.api.auth import get_current_user, require_role
from fleet_server.database import get_db
from fleet_server.models.device_group import DeviceGroup, device_group_members
from fleet_server.models.user import User
from fleet_server.schemas.device_group import (
    DeviceGroupCreate,
    DeviceGroupResponse,
    DeviceGroupUpdate,
)

router = APIRouter()


def _to_response(g: DeviceGroup) -> DeviceGroupResponse:
    ids = [m.device_id for m in (g.members or [])]
    return DeviceGroupResponse(
        id=g.id,
        name=g.name,
        description=g.description,
        device_ids=ids,
        member_count=len(ids),
        created_at=g.created_at,
        updated_at=g.updated_at,
    )


@router.get("/", response_model=list[DeviceGroupResponse])
async def list_groups(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DeviceGroup).order_by(DeviceGroup.name))
    return [_to_response(g) for g in result.scalars().all()]


@router.get("/{group_id}", response_model=DeviceGroupResponse)
async def get_group(group_id: int, db: AsyncSession = Depends(get_db)):
    g = await db.get(DeviceGroup, group_id)
    if not g:
        raise HTTPException(404, "Group not found")
    return _to_response(g)


@router.post(
    "/",
    response_model=DeviceGroupResponse,
    status_code=201,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def create_group(
    payload: DeviceGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    existing = await db.execute(
        select(DeviceGroup).where(DeviceGroup.name == payload.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "Group name already exists")

    group = DeviceGroup(
        name=payload.name,
        description=payload.description,
        created_by=user.id if user else None,
    )
    db.add(group)
    await db.flush()
    if payload.device_ids:
        await db.execute(
            device_group_members.insert().values(
                [{"group_id": group.id, "device_id": d} for d in set(payload.device_ids)]
            )
        )
    await db.commit()
    await db.refresh(group, ["members"])
    return _to_response(group)


@router.patch(
    "/{group_id}",
    response_model=DeviceGroupResponse,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def update_group(
    group_id: int,
    payload: DeviceGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    group = await db.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")

    if payload.name is not None:
        group.name = payload.name
    if payload.description is not None:
        group.description = payload.description

    if payload.device_ids is not None:
        # Full-replacement semantics: the supplied list becomes the new membership.
        await db.execute(
            delete(device_group_members).where(
                device_group_members.c.group_id == group_id
            )
        )
        if payload.device_ids:
            await db.execute(
                device_group_members.insert().values(
                    [
                        {"group_id": group_id, "device_id": d}
                        for d in set(payload.device_ids)
                    ]
                )
            )

    await db.commit()
    await db.refresh(group, ["members"])
    return _to_response(group)


@router.delete(
    "/{group_id}",
    status_code=204,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def delete_group(group_id: int, db: AsyncSession = Depends(get_db)):
    group = await db.get(DeviceGroup, group_id)
    if not group:
        raise HTTPException(404, "Group not found")
    await db.delete(group)
    await db.commit()
