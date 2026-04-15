from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CommunityCreate(BaseModel):
    community_id: str
    name: str
    description: str | None = None


class CommunityUpdate(BaseModel):
    name: str | None = None
    description: str | None = None


class CommunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    community_id: str
    name: str
    description: str | None
    created_at: datetime
