from datetime import datetime

from pydantic import BaseModel


class ProvisionRequest(BaseModel):
    device_type: str = "room_sensor"


class ProvisionJobResponse(BaseModel):
    id: str
    device_id: str
    device_type: str
    status: str
    firmware_path: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
