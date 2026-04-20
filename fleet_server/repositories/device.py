from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.models.device import Device
from fleet_server.repositories.base import BaseRepository


# Whitelisted sort columns. Anything else falls back to -last_seen.
_SORTABLE = {
    "device_id", "custom_id", "display_name", "home_id",
    "firmware_version", "status", "last_seen", "created_at", "updated_at",
}


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

    async def get_filtered_paginated(
        self,
        status: str | None = None,
        home_id: str | None = None,
        firmware_version: str | None = None,
        role: str | None = None,
        search: str | None = None,
        sort: str = "-last_seen",
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[Device], int]:
        """Paginated, filtered, sortable listing + total count in one query round.

        Returns (items, total_matching_filter). Search is substring-match,
        case-insensitive, across device_id / custom_id / display_name /
        home_id. Sort prefix '-' means descending.
        """
        conds = []
        for field, value in (
            ("status", status),
            ("home_id", home_id),
            ("firmware_version", firmware_version),
            ("role", role),
        ):
            if value is not None and value != "":
                conds.append(getattr(Device, field) == value)

        if search:
            like = f"%{search.strip()}%"
            conds.append(
                or_(
                    Device.device_id.ilike(like),
                    Device.custom_id.ilike(like),
                    Device.display_name.ilike(like),
                    Device.home_id.ilike(like),
                )
            )

        base = select(Device)
        count_q = select(func.count()).select_from(Device)
        if conds:
            base = base.where(*conds)
            count_q = count_q.where(*conds)

        reverse = sort.startswith("-")
        col_name = sort.lstrip("-")
        if col_name not in _SORTABLE:
            col_name, reverse = "last_seen", True
        col = getattr(Device, col_name)
        base = base.order_by(col.desc().nulls_last() if reverse else col.asc().nulls_last())

        page = base.offset(skip).limit(limit)
        items = list((await self.db.execute(page)).scalars().all())
        total = (await self.db.execute(count_q)).scalar_one()
        return items, total

    async def distinct_values(self, column: str) -> list[str]:
        """Whitelisted distinct-value helper for filter dropdowns."""
        if column not in {"home_id", "firmware_version", "status", "role"}:
            return []
        col = getattr(Device, column)
        q = select(col).where(col.is_not(None)).distinct().order_by(col.asc())
        return [v for v in (await self.db.execute(q)).scalars().all() if v]
