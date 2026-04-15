from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fleet_server.models.community import Community, home_community
from fleet_server.models.home import Home
from fleet_server.repositories.base import BaseRepository


class HomeRepository(BaseRepository[Home]):
    def __init__(self, db: AsyncSession):
        super().__init__(Home, db)

    async def get_with_communities(self, home_id: str) -> Home | None:
        result = await self.db.execute(
            select(Home)
            .options(selectinload(Home.communities))
            .where(Home.home_id == home_id)
        )
        return result.scalar_one_or_none()

    async def assign_community(self, home_id: str, community_id: str) -> bool:
        home = await self.get_by_id(home_id)
        community = await self.db.get(Community, community_id)
        if not home or not community:
            return False
        await self.db.execute(
            home_community.insert().values(
                home_id=home_id, community_id=community_id
            )
        )
        await self.db.commit()
        return True

    async def remove_community(self, home_id: str, community_id: str) -> bool:
        result = await self.db.execute(
            home_community.delete().where(
                (home_community.c.home_id == home_id)
                & (home_community.c.community_id == community_id)
            )
        )
        await self.db.commit()
        return result.rowcount > 0
