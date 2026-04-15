"""Alerting service tests — console channel always works, Slack/email mocked."""

import pytest
from unittest.mock import AsyncMock, patch

from fleet_server.services.alerting import AlertService, ConsoleChannel, SlackChannel


@pytest.mark.asyncio
async def test_console_alert():
    channel = ConsoleChannel()
    result = await channel.send("Test Alert", "Device esp32-001 is dead")
    assert result is True


@pytest.mark.asyncio
async def test_alert_service_dispatches_to_all_channels():
    service = AlertService()
    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock(return_value=True)
    service.channels.append(mock_channel)

    await service.device_dead(["esp32-001", "esp32-002"])

    mock_channel.send.assert_called_once()
    args = mock_channel.send.call_args[0]
    assert "2 device(s)" in args[0]
    assert "esp32-001" in args[1]
    assert "esp32-002" in args[1]


@pytest.mark.asyncio
async def test_alert_service_empty_list_no_alert():
    service = AlertService()
    mock_channel = AsyncMock()
    mock_channel.send = AsyncMock()
    service.channels.append(mock_channel)

    await service.device_dead([])

    mock_channel.send.assert_not_called()


@pytest.mark.asyncio
async def test_slack_channel_disabled_without_url():
    channel = SlackChannel()
    result = await channel.send("Test", "msg")
    assert result is False


@pytest.mark.asyncio
async def test_dead_detection_triggers_alert(db_session):
    """Integration: dead device detection triggers alert service."""
    from datetime import datetime, timedelta, timezone
    from fleet_server.models.device import Device
    from fleet_server.tasks.scheduler import check_dead_devices

    old_time = datetime.now(timezone.utc) - timedelta(seconds=120)
    device = Device(
        device_id="esp32-alert-test",
        mac="AL:ER:TT:ES:T0:01",
        firmware_version="1.0.0",
        status="alive",
        last_seen=old_time,
    )
    db_session.add(device)
    await db_session.commit()

    with patch("fleet_server.services.alerting.alert_service.device_dead", new_callable=AsyncMock) as mock_alert:
        dead_ids = await check_dead_devices(db=db_session)
        assert "esp32-alert-test" in dead_ids
        mock_alert.assert_called_once_with(["esp32-alert-test"])
