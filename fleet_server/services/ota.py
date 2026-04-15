"""OTA rollout service — orchestrates firmware updates across fleet (SRP).

Dependencies: db session, publish function, firmware service — all injected (DIP).
Strategy pattern: canary/staged/full determine device selection (OCP).
"""

import json
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.config import settings
from fleet_server.models.device import Device
from fleet_server.models.ota_event import OTAEvent
from fleet_server.services.firmware import FirmwareService

logger = logging.getLogger(__name__)

PublishFn = Callable[[str, str], Coroutine[Any, Any, None]]


class OTAService:
    def __init__(self, db: AsyncSession, publish_fn: PublishFn | None = None):
        self.db = db
        self._publish = publish_fn
        self._firmware = FirmwareService(db)

    async def start_rollout(
        self,
        target_version: str,
        strategy: str = "canary",
        canary_count: int = 2,
        target_devices: list[str] | None = None,
        target_community: str | None = None,
    ) -> list[OTAEvent]:
        """Start OTA rollout — select devices, create events, publish commands."""
        firmware = await self._firmware.get_by_version(target_version)
        if not firmware:
            raise ValueError(f"Firmware version {target_version} not found")

        devices = await self._select_devices(
            strategy, canary_count, target_devices, target_community, target_version
        )
        if not devices:
            return []

        events = []
        for device in devices:
            event = OTAEvent(
                device_id=device.device_id,
                from_version=device.firmware_version,
                to_version=target_version,
                status="pending",
            )
            self.db.add(event)
            events.append(event)

        await self.db.commit()
        for e in events:
            await self.db.refresh(e)

        # Publish OTA commands
        if self._publish:
            for device in devices:
                await self._publish_ota_command(
                    device.device_id, target_version, firmware.checksum
                )

        logger.info(
            "OTA rollout started: %s → %s (%d devices, strategy=%s)",
            target_version, strategy, len(events), strategy,
        )
        return events

    async def get_events(self, target_version: str | None = None) -> list[OTAEvent]:
        query = select(OTAEvent).order_by(OTAEvent.started_at.desc())
        if target_version:
            query = query.where(OTAEvent.to_version == target_version)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def abort_rollout(self, target_version: str) -> int:
        """Cancel all pending OTA events for a version."""
        from sqlalchemy import update

        result = await self.db.execute(
            update(OTAEvent)
            .where(OTAEvent.to_version == target_version)
            .where(OTAEvent.status.in_(["pending", "downloading", "flashing"]))
            .values(status="cancelled")
            .returning(OTAEvent.id)
        )
        cancelled = list(result.scalars().all())
        await self.db.commit()
        logger.warning("OTA rollout aborted for %s: %d events cancelled", target_version, len(cancelled))
        return len(cancelled)

    async def _select_devices(
        self,
        strategy: str,
        canary_count: int,
        target_devices: list[str] | None,
        target_community: str | None,
        target_version: str,
    ) -> list[Device]:
        """Select devices based on strategy — OCP via strategy branching."""
        query = select(Device).where(
            Device.status.in_(["alive", "unknown"]),
            Device.firmware_version != target_version,
        )

        if target_devices:
            query = query.where(Device.device_id.in_(target_devices))
        elif target_community:
            from fleet_server.models.community import home_community
            from fleet_server.models.home import Home

            query = (
                query.join(Home, Device.home_id == Home.home_id)
                .join(home_community, Home.home_id == home_community.c.home_id)
                .where(home_community.c.community_id == target_community)
            )

        if strategy == "canary":
            query = query.limit(canary_count)
        # "staged" and "full" return all matching — staged is advanced manually

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def _publish_ota_command(
        self, device_id: str, version: str, checksum: str
    ) -> None:
        if not self._publish:
            return
        topic = f"fleet/{device_id}/ota/cmd"
        base_url = settings.SERVER_URL.rstrip("/")
        payload = json.dumps({
            "version": version,
            "url": f"{base_url}/firmware/{version}/firmware.bin",
            "checksum": checksum,
        })
        await self._publish(topic, payload)
