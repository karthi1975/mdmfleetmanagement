"""MQTT transport layer — connects aiomqtt to message handlers.

This is the only file that imports aiomqtt (ISP: handlers don't depend on MQTT).
Responsibilities: connect, subscribe, route messages to handlers, publish.
Business logic lives in handlers.py, not here.
"""

import asyncio
import logging

import aiomqtt

from fleet_server.config import settings
from fleet_server.database import async_session
from fleet_server.mqtt.handlers import handle_heartbeat, handle_ota_status, handle_registration

logger = logging.getLogger(__name__)

# MQTT topic patterns — fleet management only (broadcast uses FCM, not MQTT)
TOPIC_HEARTBEAT = "fleet/+/heartbeat"
TOPIC_REGISTER = "fleet/+/register"
TOPIC_OTA_STATUS = "fleet/+/ota/status"
TOPIC_LOG = "fleet/+/log"


class MQTTClient:
    """Manages MQTT connection lifecycle and message dispatch."""

    def __init__(self):
        self._client: aiomqtt.Client | None = None
        self._listen_task: asyncio.Task | None = None

    async def start(self) -> None:
        """Connect to broker and start listening in background."""
        self._client = aiomqtt.Client(
            hostname=settings.MQTT_BROKER,
            port=settings.MQTT_PORT,
            username=settings.MQTT_USERNAME or None,
            password=settings.MQTT_PASSWORD or None,
        )
        await self._client.__aenter__()
        logger.info(
            "MQTT connected to %s:%d", settings.MQTT_BROKER, settings.MQTT_PORT
        )

        await self._client.subscribe(TOPIC_HEARTBEAT)
        await self._client.subscribe(TOPIC_REGISTER)
        await self._client.subscribe(TOPIC_OTA_STATUS)
        await self._client.subscribe(TOPIC_LOG)
        logger.info("MQTT subscribed to fleet topics")

        self._listen_task = asyncio.create_task(self._listen())

    async def stop(self) -> None:
        """Disconnect and cancel listener."""
        if self._listen_task:
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass
        if self._client:
            await self._client.__aexit__(None, None, None)
            logger.info("MQTT disconnected")

    async def publish(self, topic: str, payload: str) -> None:
        """Publish a message. Used by OTA service only (broadcast uses FCM)."""
        if self._client:
            await self._client.publish(topic, payload)
            logger.debug("MQTT published to %s", topic)

    async def _listen(self) -> None:
        """Main message loop — routes to handlers with a fresh DB session each."""
        async for message in self._client.messages:
            topic = str(message.topic)
            payload = message.payload.decode()
            parts = topic.split("/")

            if len(parts) < 3:
                continue

            device_name = parts[1]

            try:
                async with async_session() as db:
                    if topic.endswith("/heartbeat"):
                        await handle_heartbeat(device_name, payload, db)
                    elif topic.endswith("/register"):
                        await handle_registration(device_name, payload, db)
                    elif topic.endswith("/ota/status"):
                        await handle_ota_status(device_name, payload, db)
                    elif topic.endswith("/log"):
                        # Req 3: Central logging — forward to Python logger → Loki
                        logging.getLogger(f"device.{device_name}").info(payload)
            except Exception:
                logger.exception("Error handling MQTT message on %s", topic)


# Module-level singleton — started/stopped via FastAPI lifespan
mqtt_client = MQTTClient()
