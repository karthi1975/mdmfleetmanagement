"""Device groups — reusable named selections of devices.

Static membership, not dynamic-by-query. The home / firmware_version /
status filter pickers already cover the dynamic case; device_groups
exist so admins can freeze a specific cohort (e.g. a canary holdback,
a pilot install batch) that wouldn't otherwise be expressible as a
single filter.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


device_group_members = Table(
    "device_group_members",
    Base.metadata,
    Column(
        "group_id",
        Integer,
        ForeignKey("device_groups.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "device_id",
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class DeviceGroup(Base):
    __tablename__ = "device_groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    members: Mapped[list["Device"]] = relationship(
        secondary=device_group_members, lazy="selectin"
    )
