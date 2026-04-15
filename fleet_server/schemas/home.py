from datetime import datetime

from pydantic import BaseModel, ConfigDict


class HomeCreate(BaseModel):
    home_id: str
    patient_name: str
    address: str | None = None


class HomeUpdate(BaseModel):
    patient_name: str | None = None
    address: str | None = None


class HomeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    home_id: str
    patient_name: str
    address: str | None
    created_at: datetime


class HomeWithCommunitiesResponse(HomeResponse):
    communities: list["CommunityResponse"] = []


# Avoid circular import — use forward ref
from fleet_server.schemas.community import CommunityResponse  # noqa: E402, F811

HomeWithCommunitiesResponse.model_rebuild()
