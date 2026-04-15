from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class Home(Base):
    __tablename__ = "homes"

    home_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_name: Mapped[str] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    devices: Mapped[list["Device"]] = relationship(back_populates="home")
    communities: Mapped[list["Community"]] = relationship(
        secondary="home_community", back_populates="homes"
    )
