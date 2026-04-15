"""Firebase Cloud Messaging client — push notifications to iOS + Android (SRP).

Single responsibility: send push notifications via FCM HTTP v1 API.
Injected into BroadcastService as the push transport (DIP).

FCM topic mapping:
  community_id "nrh"    → FCM topic "nrh"
  community_id "kaiser" → FCM topic "kaiser"

Mobile app subscribes to FCM topics on login — FCM handles fan-out.
"""

import json
import logging

import httpx

from fleet_server.config import settings

logger = logging.getLogger(__name__)

FCM_URL = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


class FCMClient:
    """Firebase Cloud Messaging push client."""

    def __init__(self):
        self._project_id = settings.FCM_PROJECT_ID
        self._credentials_path = settings.FCM_CREDENTIALS_PATH
        self._enabled = bool(self._project_id)

    async def push_to_topic(
        self,
        topic: str,
        title: str,
        body: str,
        priority: str = "normal",
    ) -> bool:
        """Push notification to all devices subscribed to an FCM topic.

        Args:
            topic: FCM topic name (matches community_id)
            title: Notification title (community name)
            body: Notification body (broadcast message)
            priority: "normal" or "urgent" (maps to FCM priority)

        Returns True on success, False on failure.
        """
        if not self._enabled:
            logger.debug("FCM disabled (no project ID) — skipping push for topic '%s'", topic)
            return True  # Return True so broadcast still records as sent

        fcm_priority = "high" if priority == "urgent" else "normal"

        payload = {
            "message": {
                "topic": topic,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "android": {
                    "priority": fcm_priority,
                },
                "apns": {
                    "headers": {
                        "apns-priority": "10" if priority == "urgent" else "5",
                    },
                },
                "data": {
                    "community_id": topic,
                    "type": "broadcast",
                    "priority": priority,
                },
            }
        }

        try:
            access_token = await self._get_access_token()
            url = FCM_URL.format(project=self._project_id)

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {access_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )

            if resp.status_code == 200:
                logger.info("FCM push success: topic=%s", topic)
                return True

            logger.error("FCM push failed: %d %s", resp.status_code, resp.text)
            return False

        except Exception:
            logger.exception("FCM push error for topic=%s", topic)
            return False

    async def _get_access_token(self) -> str:
        """Get OAuth2 access token from service account credentials.

        In production, use google-auth library:
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(path)
            credentials.refresh(Request())
            return credentials.token

        For now, returns empty string (FCM disabled in dev).
        """
        # TODO: Implement with google-auth when FCM credentials are available
        return ""


# Module-level singleton
fcm_client = FCMClient()
