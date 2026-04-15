"""Firmware service — upload, validate, list firmware versions (SRP)."""

import hashlib
import logging
from pathlib import Path

import aiofiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.config import settings
from fleet_server.models.firmware import FirmwareVersion

logger = logging.getLogger(__name__)


class FirmwareService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upload(
        self, version: str, content: bytes, release_notes: str = "",
    ) -> FirmwareVersion:
        """Save firmware binary and create DB record."""
        checksum = hashlib.sha256(content).hexdigest()

        path = Path(settings.FIRMWARE_STORAGE_PATH) / version
        path.mkdir(parents=True, exist_ok=True)
        binary_path = path / "firmware.bin"

        async with aiofiles.open(binary_path, "wb") as f:
            await f.write(content)

        fw = FirmwareVersion(
            version=version,
            binary_path=str(binary_path),
            checksum=checksum,
            release_notes=release_notes,
        )
        self.db.add(fw)
        await self.db.commit()
        await self.db.refresh(fw)
        logger.info("Firmware %s uploaded (%d bytes, sha256=%s)", version, len(content), checksum[:16])
        return fw

    async def get_by_version(self, version: str) -> FirmwareVersion | None:
        result = await self.db.execute(
            select(FirmwareVersion).where(FirmwareVersion.version == version)
        )
        return result.scalar_one_or_none()

    async def get_all(self) -> list[FirmwareVersion]:
        result = await self.db.execute(
            select(FirmwareVersion).order_by(FirmwareVersion.created_at.desc())
        )
        return list(result.scalars().all())
