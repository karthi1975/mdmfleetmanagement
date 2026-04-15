"""Alerting service — notifies when devices go dead (SRP).

Supports multiple channels: Slack webhook, email (SendGrid), console log.
New channels added by implementing AlertChannel (OCP).
Injected into scheduler — no direct dependency on transport (DIP).
"""

import logging
from abc import ABC, abstractmethod

import httpx

from fleet_server.config import settings

logger = logging.getLogger(__name__)


class AlertChannel(ABC):
    """Base class for alert delivery channels (OCP — add new channels here)."""

    @abstractmethod
    async def send(self, subject: str, message: str) -> bool: ...


class SlackChannel(AlertChannel):
    """Send alerts to Slack via incoming webhook."""

    async def send(self, subject: str, message: str) -> bool:
        if not settings.SLACK_WEBHOOK_URL:
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    settings.SLACK_WEBHOOK_URL,
                    json={"text": f"*{subject}*\n{message}"},
                    timeout=10.0,
                )
            return resp.status_code == 200
        except Exception:
            logger.exception("Slack alert failed")
            return False


class EmailChannel(AlertChannel):
    """Send alerts via SendGrid API."""

    async def send(self, subject: str, message: str) -> bool:
        if not settings.SENDGRID_API_KEY:
            return False
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.sendgrid.com/v3/mail/send",
                    headers={"Authorization": f"Bearer {settings.SENDGRID_API_KEY}"},
                    json={
                        "personalizations": [{"to": [{"email": settings.ALERT_EMAIL}]}],
                        "from": {"email": "fleet@tetradapt.com"},
                        "subject": subject,
                        "content": [{"type": "text/plain", "value": message}],
                    },
                    timeout=10.0,
                )
            return resp.status_code in (200, 202)
        except Exception:
            logger.exception("Email alert failed")
            return False


class ConsoleChannel(AlertChannel):
    """Log alerts to console — always enabled, fallback channel."""

    async def send(self, subject: str, message: str) -> bool:
        logger.warning("ALERT: %s — %s", subject, message)
        return True


class AlertService:
    """Dispatches alerts to all configured channels."""

    def __init__(self):
        self.channels: list[AlertChannel] = [ConsoleChannel()]
        if settings.SLACK_WEBHOOK_URL:
            self.channels.append(SlackChannel())
        if settings.SENDGRID_API_KEY:
            self.channels.append(EmailChannel())

    async def device_dead(self, device_ids: list[str]) -> None:
        if not device_ids:
            return
        count = len(device_ids)
        subject = f"Fleet Alert: {count} device(s) went offline"
        message = (
            f"{count} device(s) have not sent a heartbeat in 90+ seconds:\n"
            + "\n".join(f"  • {did}" for did in device_ids)
        )
        for channel in self.channels:
            await channel.send(subject, message)


alert_service = AlertService()
