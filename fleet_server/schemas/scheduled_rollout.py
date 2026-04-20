from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScheduledRolloutCreate(BaseModel):
    target_version: str
    strategy: str = Field(default="full", pattern=r"^(full|canary|staged)$")
    target_devices: list[str] = Field(default_factory=list)
    canary_count: int | None = None
    fire_at: datetime


class ScheduledRolloutResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_version: str
    strategy: str
    target_devices: list[str]
    canary_count: int | None
    fire_at: datetime
    status: str
    created_at: datetime
    fired_at: datetime | None
    error: str | None
