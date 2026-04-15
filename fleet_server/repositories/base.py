"""Base repository — generic CRUD operations (Open/Closed Principle).

Concrete repositories extend this with entity-specific queries.
All DB access goes through repositories, not directly in route handlers (SRP).
"""

from typing import Any, Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic async CRUD repository for any SQLAlchemy model."""

    def __init__(self, model: type[ModelType], db: AsyncSession):
        self.model = model
        self.db = db

    async def get_by_id(self, pk: Any) -> ModelType | None:
        return await self.db.get(self.model, pk)

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 50,
        filters: dict[str, Any] | None = None,
    ) -> list[ModelType]:
        query = select(self.model)
        if filters:
            for field, value in filters.items():
                if value is not None and hasattr(self.model, field):
                    query = query.where(getattr(self.model, field) == value)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> ModelType:
        instance = self.model(**data)
        self.db.add(instance)
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def update(self, pk: Any, data: dict[str, Any]) -> ModelType | None:
        instance = await self.get_by_id(pk)
        if not instance:
            return None
        for field, value in data.items():
            setattr(instance, field, value)
        await self.db.commit()
        await self.db.refresh(instance)
        return instance

    async def delete(self, pk: Any) -> bool:
        instance = await self.get_by_id(pk)
        if not instance:
            return False
        await self.db.delete(instance)
        await self.db.commit()
        return True
