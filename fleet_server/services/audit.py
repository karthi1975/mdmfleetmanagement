"""Audit service — records all mutations for compliance (SRP).

Every create/update/delete across all resources is logged with
who did it, what changed, and when. HIPAA compliance requirement.

Injected as a dependency — routes call audit.log() after mutations (DIP).
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from fleet_server.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


class AuditService:
    def __init__(self, db: AsyncSession, user_id: str | None = None):
        self.db = db
        self.user_id = user_id

    async def log(
        self,
        action: str,
        resource: str,
        details: dict | None = None,
    ) -> AuditLog:
        """Record an audit event.

        Args:
            action: create, update, delete, ota_start, broadcast_send, login
            resource: device, home, community, firmware, broadcast, user
            details: JSON-serializable context (IDs, changed fields, etc.)
        """
        entry = AuditLog(
            user_id=self.user_id,
            action=action,
            resource=resource,
            details=details,
        )
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)

        logger.info(
            "AUDIT: user=%s action=%s resource=%s",
            self.user_id or "system", action, resource,
        )
        return entry
