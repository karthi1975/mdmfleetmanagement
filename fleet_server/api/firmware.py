"""Firmware upload and listing API."""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.api.auth import get_current_user, require_role
from fleet_server.database import get_db
from fleet_server.models.user import User
from fleet_server.schemas.firmware import FirmwareResponse
from fleet_server.services.audit import AuditService
from fleet_server.services.firmware import FirmwareService

router = APIRouter()


def get_service(db: AsyncSession = Depends(get_db)) -> FirmwareService:
    return FirmwareService(db)


def get_audit(db: AsyncSession = Depends(get_db)) -> AuditService:
    return AuditService(db)


@router.post(
    "/",
    response_model=FirmwareResponse,
    status_code=201,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def upload_firmware(
    version: str = Form(...),
    release_notes: str = Form(""),
    file: UploadFile = File(...),
    service: FirmwareService = Depends(get_service),
    audit: AuditService = Depends(get_audit),
    user: User = Depends(get_current_user),
):
    existing = await service.get_by_version(version)
    if existing:
        raise HTTPException(status_code=409, detail="Version already exists")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Empty file")

    fw = await service.upload(version, content, release_notes)
    audit.user_id = user.id if user else None
    await audit.log(
        "upload",
        "firmware",
        {"version": version, "size_bytes": len(content), "checksum": fw.checksum},
    )
    return fw


@router.get("/", response_model=list[FirmwareResponse])
async def list_firmware(
    service: FirmwareService = Depends(get_service),
):
    return await service.get_all()


@router.get("/{version}", response_model=FirmwareResponse)
async def get_firmware(
    version: str,
    service: FirmwareService = Depends(get_service),
):
    fw = await service.get_by_version(version)
    if not fw:
        raise HTTPException(status_code=404, detail="Version not found")
    return fw
