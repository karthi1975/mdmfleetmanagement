"""Broadcast service — push notifications to SmartHome iOS/Android apps via FCM (SRP).

Uses Firebase Cloud Messaging (FCM) for delivery to both iOS and Android.
Apps subscribe to FCM topics by community (e.g., "nrh", "kaiser").
Fleet API publishes to FCM → Firebase handles push to all platforms.

Dependencies (db session, push function) are injected (DIP).
The push callable is an abstraction — production injects FCM sender,
tests inject a mock. Transport-agnostic (OCP).
"""

import json
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fleet_server.models.broadcast import Broadcast, BroadcastAck
from fleet_server.models.community import Community

logger = logging.getLogger(__name__)

# Type alias for the push function — production uses FCM, tests use mock
PushFn = Callable[[str, str, str, str], Coroutine[Any, Any, bool]]


class BroadcastService:
    """Push notifications to SmartHome apps via FCM topic-based delivery."""

    def __init__(self, db: AsyncSession, push_fn: PushFn | None = None):
        self.db = db
        self._push = push_fn

    async def send(
        self,
        community_ids: list[str],
        message: str,
        msg_type: str = "notification",
        priority: str = "normal",
        scheduled_at: datetime | None = None,
        sent_by: str | None = None,
    ) -> list[Broadcast]:
        """Create broadcast records and push via FCM to community topics.

        Each community maps to an FCM topic. Apps subscribed to that
        topic receive the push notification on iOS and Android.
        """
        broadcasts = []
        for community_id in community_ids:
            community = await self.db.get(Community, community_id)
            if not community:
                logger.warning("Skipping unknown community: %s", community_id)
                continue

            broadcast = Broadcast(
                community_id=community_id,
                message=message,
                type=msg_type,
                priority=priority,
                scheduled_at=scheduled_at,
                sent_by=sent_by,
            )

            if scheduled_at is None:
                broadcast.sent_at = datetime.now(timezone.utc)

            self.db.add(broadcast)
            broadcasts.append(broadcast)

        await self.db.commit()

        for b in broadcasts:
            await self.db.refresh(b)

        # Push immediate broadcasts via FCM
        if scheduled_at is None and self._push:
            for b in broadcasts:
                await self._push_broadcast(b)

        return broadcasts

    async def get_by_id(self, broadcast_id: int) -> Broadcast | None:
        result = await self.db.execute(
            select(Broadcast)
            .options(selectinload(Broadcast.acks))
            .where(Broadcast.id == broadcast_id)
        )
        return result.scalar_one_or_none()

    async def get_all(
        self,
        community_id: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Broadcast]:
        query = select(Broadcast).order_by(Broadcast.created_at.desc())
        if community_id:
            query = query.where(Broadcast.community_id == community_id)
        query = query.offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def record_ack(
        self,
        broadcast_id: int,
        home_id: str,
        status: str,
        received_at: datetime | None = None,
    ) -> BroadcastAck | None:
        """Record delivery ACK from a SmartHome mobile app."""
        broadcast = await self.db.get(Broadcast, broadcast_id)
        if not broadcast:
            return None

        ack = BroadcastAck(
            broadcast_id=broadcast_id,
            home_id=home_id,
            status=status,
            received_at=received_at,
        )
        self.db.add(ack)
        await self.db.commit()
        await self.db.refresh(ack)
        logger.info(
            "Broadcast %d ACK from %s: %s", broadcast_id, home_id, status
        )
        return ack

    async def get_delivery_stats(self, broadcast_id: int) -> dict:
        broadcast = await self.get_by_id(broadcast_id)
        if not broadcast:
            return {}

        community = await self.db.execute(
            select(Community)
            .options(selectinload(Community.homes))
            .where(Community.community_id == broadcast.community_id)
        )
        community_obj = community.scalar_one_or_none()
        total_targets = len(community_obj.homes) if community_obj else 0

        return {
            "broadcast_id": broadcast_id,
            "total_targets": total_targets,
            "delivered_count": len(broadcast.acks),
            "acks": broadcast.acks,
        }

    async def _push_broadcast(self, broadcast: Broadcast) -> None:
        """Push to FCM topic — all subscribed iOS/Android apps get notified."""
        if not self._push:
            return

        community = await self.db.get(Community, broadcast.community_id)
        title = community.name if community else broadcast.community_id

        success = await self._push(
            broadcast.community_id,
            title,
            broadcast.message,
            broadcast.priority,
        )
        if success:
            logger.info(
                "Broadcast %d pushed via FCM to topic '%s'",
                broadcast.id, broadcast.community_id,
            )
        else:
            logger.error(
                "Broadcast %d FCM push failed for topic '%s'",
                broadcast.id, broadcast.community_id,
            )
