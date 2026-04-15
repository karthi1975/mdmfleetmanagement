from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.models.device import Device
from fleet_server.repositories.base import BaseRepository


class DeviceRepository(BaseRepository[Device]):
    def __init__(self, db: AsyncSession):
        super().__init__(Device, db)

    async def get_filtered(
        self,
        status: str | None = None,
        home_id: str | None = None,
        role: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Device]:
        filters = {"status": status, "home_id": home_id, "role": role}
        return await self.get_all(skip=skip, limit=limit, filters=filters)
