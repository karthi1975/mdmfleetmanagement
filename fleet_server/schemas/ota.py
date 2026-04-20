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


class OTARolloutPreview(BaseModel):
    """Dry-run output: what a rollout would affect, without committing."""
    target_version: str
    strategy: str
    total: int
    by_status: dict[str, int]
    by_current_version: dict[str, int]
    by_home: dict[str, int]
    device_ids: list[str]


class OTACampaign(BaseModel):
    """A rollout campaign (grouped events) as surfaced on the history panel."""
    to_version: str
    started_at: datetime
    total: int
    success: int
    failed: int
    in_flight: int
