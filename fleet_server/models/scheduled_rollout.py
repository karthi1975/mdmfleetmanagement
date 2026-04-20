"""Scheduled OTA rollouts — fire at a specific time instead of now.

The scheduler polls pending rows once per minute and triggers the
OTA service when fire_at <= now(). Once fired, status flips to
'fired' and the event is linked to the normal ota_events machinery.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class ScheduledRollout(Base):
    __tablename__ = "scheduled_rollouts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    target_version: Mapped[str] = mapped_column(
        ForeignKey("firmware_versions.version")
    )
    strategy: Mapped[str] = mapped_column(String(16), default="full")
    target_devices: Mapped[list[str]] = mapped_column(JSON)  # list of device_ids
    canary_count: Mapped[int | None] = mapped_column(nullable=True)
    fire_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # pending | fired | cancelled | failed
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    fired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
