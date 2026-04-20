"""APScheduler setup — background jobs running on the FastAPI event loop.

Each job is a standalone async function with its own DB session (SRP).
The scheduler is a thin orchestrator — it doesn't contain business logic.
"""

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.database import async_session
from fleet_server.models.device import Device
from fleet_server.models.scheduled_rollout import ScheduledRollout

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


async def fire_due_scheduled_rollouts(db: AsyncSession | None = None) -> list[int]:
    """Trigger scheduled rollouts whose fire_at is due.

    Runs once a minute. For each pending row with fire_at <= now, calls
    OTAService.start_rollout and flips the row to 'fired' — or 'failed'
    with the error string, so the admin UI can surface the reason.
    with_for_update(skip_locked=True) protects against a second worker
    in the future racing the same row.
    """
    now = datetime.now(timezone.utc)

    async def _execute(session: AsyncSession) -> list[int]:
        # Late imports keep this module importable during tests that
        # don't want to pull in MQTT / OTA service graphs.
        from fleet_server.mqtt.client import mqtt_client
        from fleet_server.services.ota import OTAService

        result = await session.execute(
            select(ScheduledRollout)
            .where(ScheduledRollout.status == "pending")
            .where(ScheduledRollout.fire_at <= now)
            .with_for_update(skip_locked=True)
        )
        due = list(result.scalars().all())
        fired: list[int] = []
        service = OTAService(session, publish_fn=mqtt_client.publish)
        for row in due:
            try:
                await service.start_rollout(
                    target_version=row.target_version,
                    strategy=row.strategy,
                    canary_count=row.canary_count or 2,
                    target_devices=row.target_devices,
                )
                row.status = "fired"
                row.fired_at = datetime.now(timezone.utc)
                fired.append(row.id)
                logger.info(
                    "Scheduled rollout #%d fired → %s on %d devices",
                    row.id, row.target_version, len(row.target_devices),
                )
            except Exception as err:  # noqa: BLE001
                row.status = "failed"
                row.error = str(err)[:1000]
                logger.error("Scheduled rollout #%d failed: %s", row.id, err)
        await session.commit()
        return fired

    if db is not None:
        return await _execute(db)

    async with async_session() as session:
        return await _execute(session)


# Register jobs
scheduler.add_job(
    check_dead_devices,
    trigger=IntervalTrigger(seconds=CHECK_INTERVAL_SECONDS),
    id="check_dead_devices",
    replace_existing=True,
)
scheduler.add_job(
    fire_due_scheduled_rollouts,
    trigger=IntervalTrigger(seconds=60),
    id="fire_due_scheduled_rollouts",
    replace_existing=True,
)
