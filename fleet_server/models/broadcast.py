from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    community_id: Mapped[str] = mapped_column(ForeignKey("communities.community_id"))
    message: Mapped[str] = mapped_column(Text)
    type: Mapped[str] = mapped_column(String(16))
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    community: Mapped["Community"] = relationship()
    acks: Mapped[list["BroadcastAck"]] = relationship(back_populates="broadcast")


class BroadcastAck(Base):
    __tablename__ = "broadcast_acks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    broadcast_id: Mapped[int] = mapped_column(ForeignKey("broadcasts.id"))
    home_id: Mapped[str] = mapped_column(ForeignKey("homes.home_id"))
    status: Mapped[str] = mapped_column(String(16))
    received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    broadcast: Mapped["Broadcast"] = relationship(back_populates="acks")
