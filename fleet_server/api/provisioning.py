"""Provisioning + per-device firmware delivery endpoints.

- POST /provisioning/provision        — start a new device + compile job
- GET  /provisioning/jobs/{job_id}    — poll job status
- GET  /provisioning/devices/{id}/firmware.bin   — serve compiled binary
- GET  /provisioning/devices/{id}/manifest.json  — ESP Web Tools manifest
"""

from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.api.auth import require_role
from fleet_server.config import settings
from fleet_server.database import get_db
from fleet_server.models.provision_job import ProvisionJob
from fleet_server.schemas.provisioning import ProvisionJobResponse, ProvisionRequest
from fleet_server.services.provisioning import ProvisioningService

router = APIRouter()


@router.post(
    "/provision",
    response_model=ProvisionJobResponse,
    status_code=202,
    dependencies=[Depends(require_role("admin", "operator"))],
)
async def provision(
    payload: ProvisionRequest,
    background: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    svc = ProvisioningService(db)
    job = await svc.start_job(payload.device_type)
    background.add_task(ProvisioningService.run_job, job.id)
    return job


@router.get(
    "/jobs/{job_id}",
    response_model=ProvisionJobResponse,
    dependencies=[Depends(require_role("admin", "operator", "viewer"))],
)
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = (
        await db.execute(select(ProvisionJob).where(ProvisionJob.id == job_id))
    ).scalar_one_or_none()
    if not job:
        raise HTTPException(404, "job not found")
    return job


@router.get("/devices/{device_id}/firmware.bin")
async def download_firmware(device_id: str):
    path = Path(settings.FIRMWARE_STORAGE_PATH) / device_id / "firmware.bin"
    if not path.exists():
        raise HTTPException(404, "firmware not built yet")
    return FileResponse(
        str(path),
        media_type="application/octet-stream",
        filename=f"{device_id}.bin",
    )


@router.get("/devices/{device_id}/manifest.json")
async def manifest(device_id: str):
    """ESP Web Tools install manifest — points the browser at firmware.bin."""
    return JSONResponse(
        {
            "name": f"SmartHome {device_id}",
            "version": "1.0.0",
            "home_assistant_domain": "esphome",
            "new_install_prompt_erase": True,
            "builds": [
                {
                    "chipFamily": "ESP32",
                    "parts": [
                        {
                            "path": f"{settings.SERVER_URL}/api/provisioning/devices/{device_id}/firmware.bin",
                            "offset": 0,
                        }
                    ],
                }
            ],
        }
    )
