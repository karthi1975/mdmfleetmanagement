from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Device(Base):
    __tablename__ = "devices"

    device_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    mac: Mapped[str] = mapped_column(String(17), unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    firmware_version: Mapped[str] = mapped_column(String(32), nullable=True)
    target_firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    device_type: Mapped[str] = mapped_column(String(32), default="room_sensor")
    provision_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), default="sensor")
    status: Mapped[str] = mapped_column(String(16), default="unknown")
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    home_id: Mapped[str | None] = mapped_column(
        ForeignKey("homes.home_id"), nullable=True
    )
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    heap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uptime: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    home: Mapped["Home | None"] = relationship(back_populates="devices")
