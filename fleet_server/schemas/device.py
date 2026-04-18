from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DeviceCreate(BaseModel):
    device_id: str
    mac: str
    firmware_version: str
    role: str = "sensor"
    home_id: str | None = None


class DeviceUpdate(BaseModel):
    firmware_version: str | None = None
    role: str | None = None
    status: str | None = None
    home_id: str | None = None


class DeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    mac: str | None
    display_name: str | None
    custom_id: str | None
    firmware_version: str | None
    role: str
    status: str
    last_seen: datetime | None
    home_id: str | None
    rssi: int | None
    heap: int | None
    uptime: int | None
    created_at: datetime
    updated_at: datetime
