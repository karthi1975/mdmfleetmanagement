from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fleet_server.models.community import Community
from fleet_server.models.home import Home
from fleet_server.repositories.base import BaseRepository


class CommunityRepository(BaseRepository[Community]):
    def __init__(self, db: AsyncSession):
        super().__init__(Community, db)

    async def get_with_homes(self, community_id: str) -> Community | None:
        result = await self.db.execute(
            select(Community)
            .options(selectinload(Community.homes))
            .where(Community.community_id == community_id)
        )
        return result.scalar_one_or_none()

    async def get_homes(self, community_id: str) -> list[Home]:
        community = await self.get_with_homes(community_id)
        if not community:
            return []
        return community.homes
