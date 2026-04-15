"""Provisioning service — render YAML, compile firmware, track job status.

Single responsibility: turn a (device_id, device_type) request into a
compiled .bin on disk and update the ProvisionJob row accordingly.

The compile is run by invoking the already-running `esphome` Docker
service via the host docker socket. fleet-api must have the docker CLI
installed and /var/run/docker.sock mounted.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.config import settings
from fleet_server.database import async_session
from fleet_server.models.device import Device
from fleet_server.models.provision_job import ProvisionJob

logger = logging.getLogger(__name__)

# These paths are relative to the project root inside the fleet-api container.
# docker-compose mounts ./esphome → /app/esphome and ./data/firmware → /data/firmware.
ESPHOME_DIR = Path("/app/esphome")
TEMPLATES_DIR = ESPHOME_DIR / "templates"
PROVISION_DIR = ESPHOME_DIR / "provision"
FIRMWARE_OUT = Path(settings.FIRMWARE_STORAGE_PATH)

_jinja = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    autoescape=select_autoescape(disabled_extensions=("j2",), default=False),
    keep_trailing_newline=True,
)


class ProvisioningService:
    """Render → compile → publish. One job, one device."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---------- public API ---------- #

    async def start_job(self, device_type: str) -> ProvisionJob:
        """Create device + job rows; caller schedules run_job() in background."""
        device_id = f"esp32-{secrets.token_hex(4)}"
        token = secrets.token_urlsafe(32)

        device = Device(
            device_id=device_id,
            device_type=device_type,
            provision_token=token,
            role="sensor",
            status="provisioning",
            firmware_version="1.0.0",
        )
        job = ProvisionJob(
            id=secrets.token_hex(16),
            device_id=device_id,
            device_type=device_type,
            status="pending",
        )
        self.db.add(device)
        self.db.add(job)
        await self.db.commit()
        await self.db.refresh(job)
        return job

    @staticmethod
    async def run_job(job_id: str) -> None:
        """Background entry point — owns its own DB session."""
        async with async_session() as db:
            svc = ProvisioningService(db)
            await svc._run(job_id)

    # ---------- internals ---------- #

    async def _run(self, job_id: str) -> None:
        job = await self._get_job(job_id)
        if not job:
            logger.error("provision job %s not found", job_id)
            return
        device = await self._get_device(job.device_id)
        if not device:
            await self._fail(job, "device row missing")
            return

        try:
            await self._set_status(job, "rendering")
            yaml_path = self._render(device)

            await self._set_status(job, "compiling")
            bin_path = await self._compile(yaml_path, device.device_id)

            job.firmware_path = str(bin_path)
            await self._set_status(job, "ready")
            logger.info("provision job %s ready: %s", job_id, bin_path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("provision job %s failed", job_id)
            await self._fail(job, str(exc))

    def _render(self, device: Device) -> Path:
        template = _jinja.get_template(f"{device.device_type}.yaml.j2")
        rendered = template.render(
            device_id=device.device_id,
            firmware_version=device.firmware_version or "1.0.0",
            fleet_url=settings.SERVER_URL,
            provision_token=device.provision_token,
        )
        PROVISION_DIR.mkdir(parents=True, exist_ok=True)
        path = PROVISION_DIR / f"{device.device_id}.yaml"
        path.write_text(rendered)
        return path

    async def _compile(self, yaml_path: Path, device_id: str) -> Path:
        """Run `docker run --rm esphome compile <rel>` against the host daemon.

        Bind mounts use HOST paths because docker.sock is the host daemon.
        Returns the path to the published .bin under FIRMWARE_OUT/<device_id>/.
        """
        host_root = settings.HOST_PROJECT_DIR.rstrip("/")
        rel = f"provision/{yaml_path.name}"
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{host_root}/esphome:/config",
            settings.ESPHOME_IMAGE,
            "compile", rel,
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            tail = (stdout or b"").decode(errors="replace")[-2000:]
            raise RuntimeError(f"esphome compile failed: {tail}")

        # ESPHome writes build artifacts under <yaml_dir>/.esphome/build/<name>/.
        # Search broadly for the freshly built firmware.bin.
        candidates = sorted(
            ESPHOME_DIR.rglob(f".esphome/build/{device_id}/**/firmware.factory.bin")
        ) or sorted(
            ESPHOME_DIR.rglob(f".esphome/build/{device_id}/**/firmware.bin")
        )
        if not candidates:
            raise RuntimeError(f"firmware.bin not found for {device_id}")
        src = candidates[-1]

        out_dir = FIRMWARE_OUT / device_id
        out_dir.mkdir(parents=True, exist_ok=True)
        dst = out_dir / "firmware.bin"
        shutil.copy2(src, dst)
        return dst

    # ---------- DB helpers ---------- #

    async def _get_job(self, job_id: str) -> ProvisionJob | None:
        return (
            await self.db.execute(
                select(ProvisionJob).where(ProvisionJob.id == job_id)
            )
        ).scalar_one_or_none()

    async def _get_device(self, device_id: str) -> Device | None:
        return (
            await self.db.execute(
                select(Device).where(Device.device_id == device_id)
            )
        ).scalar_one_or_none()

    async def _set_status(self, job: ProvisionJob, status: str) -> None:
        job.status = status
        await self.db.commit()

    async def _fail(self, job: ProvisionJob, error: str) -> None:
        job.status = "failed"
        job.error = error
        await self.db.commit()
