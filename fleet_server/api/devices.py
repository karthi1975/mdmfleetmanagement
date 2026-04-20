"""Device CRUD — delegates to repository, logs mutations to audit (SRP)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import get_db
from fleet_server.repositories.device import DeviceRepository
from fleet_server.schemas.device import (
    DeviceCreate,
    DeviceListResponse,
    DeviceResponse,
    DeviceUpdate,
)
from fleet_server.services.audit import AuditService

router = APIRouter()


def get_repo(db: AsyncSession = Depends(get_db)) -> DeviceRepository:
    return DeviceRepository(db)


def get_audit(db: AsyncSession = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.get("/", response_model=DeviceListResponse)
async def list_devices(
    status: str | None = None,
    home_id: str | None = None,
    firmware_version: str | None = None,
    role: str | None = None,
    search: str | None = None,
    sort: str = "-last_seen",
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    repo: DeviceRepository = Depends(get_repo),
):
    items, total = await repo.get_filtered_paginated(
        status=status,
        home_id=home_id,
        firmware_version=firmware_version,
        role=role,
        search=search,
        sort=sort,
        skip=skip,
        limit=limit,
    )
    return DeviceListResponse(items=items, total=total, limit=limit, offset=skip)


# Distinct-value helper for filter dropdowns (home_id, firmware_version, ...).
# Defined before the /{device_id} catch-all so the path matches first.
@router.get("/facets/{column}", response_model=list[str])
async def list_facet(
    column: str,
    repo: DeviceRepository = Depends(get_repo),
):
    return await repo.distinct_values(column)


@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    repo: DeviceRepository = Depends(get_repo),
):
    device = await repo.get_by_id(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return device


@router.post("/", response_model=DeviceResponse, status_code=201)
async def create_device(
    payload: DeviceCreate,
    repo: DeviceRepository = Depends(get_repo),
    audit: AuditService = Depends(get_audit),
):
    existing = await repo.get_by_id(payload.device_id)
    if existing:
        raise HTTPException(status_code=409, detail="Device already exists")
    device = await repo.create(payload.model_dump())
    await audit.log("create", "device", {"device_id": device.device_id})
    return device


@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    payload: DeviceUpdate,
    repo: DeviceRepository = Depends(get_repo),
    audit: AuditService = Depends(get_audit),
):
    changes = payload.model_dump(exclude_unset=True)
    device = await repo.update(device_id, changes)
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await audit.log("update", "device", {"device_id": device_id, "changes": changes})
    return device


@router.delete("/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    repo: DeviceRepository = Depends(get_repo),
    audit: AuditService = Depends(get_audit),
):
    deleted = await repo.delete(device_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Device not found")
    await audit.log("delete", "device", {"device_id": device_id})
