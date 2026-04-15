from datetime import datetime

from pydantic import BaseModel, ConfigDict


class FirmwareResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: str
    binary_path: str
    checksum: str
    release_notes: str | None
    created_at: datetime
