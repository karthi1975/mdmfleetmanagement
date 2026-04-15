from datetime import datetime

from pydantic import BaseModel, ConfigDict


class OTARolloutCreate(BaseModel):
    target_version: str
    strategy: str = "canary"
    canary_count: int = 2
    target_devices: list[str] | None = None
    target_community: str | None = None


class OTAEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    device_id: str
    from_version: str
    to_version: str
    status: str
    started_at: datetime
    completed_at: datetime | None


class OTARolloutResponse(BaseModel):
    target_version: str
    strategy: str
    total_devices: int
    events: list[OTAEventResponse]
