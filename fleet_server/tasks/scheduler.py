"""APScheduler setup — background jobs running on the FastAPI event loop.

Each job is a standalone async function with its own DB session (SRP).
The scheduler is a thin orchestrator — it doesn't contain business logic.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import async_session
from fleet_server.models.device import Device

logger = logging.getLogger(__name__)

DEAD_THRESHOLD_SECONDS = 90
CHECK_INTERVAL_SECONDS = 60

scheduler = AsyncIOScheduler()


async def check_dead_devices(db: AsyncSession | None = None) -> list[str]:
    """Mark devices as dead if no heartbeat received within threshold.

    Args:
        db: Optional session for testing. If None, creates its own session.
            This follows DIP — callers inject the dependency, production
            uses the default.

    Returns list of device IDs that were marked dead.
    """
    threshold = datetime.now(timezone.utc) - timedelta(seconds=DEAD_THRESHOLD_SECONDS)

    async def _execute(session: AsyncSession) -> list[str]:
        result = await session.execute(
            update(Device)
            .where(Device.status == "alive")
            .where(Device.last_seen < threshold)
            .values(status="dead")
            .returning(Device.device_id)
        )
        dead_ids = list(result.scalars().all())
        await session.commit()
        if dead_ids:
            logger.warning(
                "Devices marked dead (no heartbeat >%ds): %s",
                DEAD_THRESHOLD_SECONDS, dead_ids,
            )
            # Send alerts (Slack, email, console)
            from fleet_server.services.alerting import alert_service
            await alert_service.device_dead(dead_ids)
        return dead_ids

    if db is not None:
        return await _execute(db)

    async with async_session() as session:
        return await _execute(session)


# Register the job
scheduler.add_job(
    check_dead_devices,
    trigger=IntervalTrigger(seconds=CHECK_INTERVAL_SECONDS),
    id="check_dead_devices",
    replace_existing=True,
)
