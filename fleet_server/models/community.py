from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

home_community = Table(
    "home_community",
    Base.metadata,
    Column("home_id", ForeignKey("homes.home_id"), primary_key=True),
    Column("community_id", ForeignKey("communities.community_id"), primary_key=True),
)


class Community(Base):
    __tablename__ = "communities"

    community_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    homes: Mapped[list["Home"]] = relationship(
        secondary="home_community", back_populates="communities"
    )
