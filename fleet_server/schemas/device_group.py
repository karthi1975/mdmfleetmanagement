from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DeviceGroupCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    device_ids: list[str] = Field(default_factory=list)


class DeviceGroupUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    device_ids: list[str] | None = None  # full replacement when provided


class DeviceGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str | None
    device_ids: list[str]
    member_count: int
    created_at: datetime
    updated_at: datetime
