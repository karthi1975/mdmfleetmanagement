from datetime import datetime

from pydantic import BaseModel, ConfigDict


class BroadcastCreate(BaseModel):
    community_ids: list[str]
    message: str
    type: str = "notification"  # notification, alert, info
    priority: str = "normal"  # normal, urgent
    scheduled_at: datetime | None = None
    sent_by: str | None = None


class BroadcastResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    community_id: str
    message: str
    type: str
    priority: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    sent_by: str | None
    created_at: datetime


class BroadcastAckCreate(BaseModel):
    msg_id: int
    status: str  # delivered, read, dismissed
    received_at: datetime | None = None


class BroadcastAckResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    broadcast_id: int
    home_id: str
    status: str
    received_at: datetime | None


class BroadcastDetailResponse(BroadcastResponse):
    acks: list[BroadcastAckResponse] = []
    total_targets: int = 0
    delivered_count: int = 0
