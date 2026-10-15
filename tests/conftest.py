"""Shared pytest fixtures."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi import Hive
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map


@pytest.fixture
async def file_session():
    """Hive session loaded from the bundled data.json fixture."""
    async with Hive(username="use@file.com", password="") as hive:
        await hive.start_session({})
        yield hive


@pytest.fixture
def fake_session():
    """Lightweight stub session for module-level tests."""
    session = MagicMock()
    session.data = Map(
        {
            "products": {},
            "devices": {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    session.config = SessionConfig()
    session.helper = MagicMock()
    session.helper.get_schedule_nnl = MagicMock(return_value={})
    session.helper.device_recovered = MagicMock()
    session.helper.error_check = AsyncMock()
    session.attr = MagicMock()
    session.attr.online_offline = AsyncMock(return_value=True)
    session.attr.state_attributes = AsyncMock(return_value={})
    session.api = MagicMock()
    session.api.set_state = AsyncMock(return_value={"original": 200, "parsed": {}})
    session.api.set_action = AsyncMock(return_value={"original": 200, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return session


def make_device(hive_id="prod-1", device_id="dev-1", hive_type="heating", **kwargs):
    """Build a Device with sensible defaults for tests."""
    ha_type = kwargs.pop("ha_type", "climate")
    return Device(
        hive_id=hive_id,
        hive_name="Test",
        hive_type=hive_type,
        ha_type=ha_type,
        device_id=device_id,
        device_name="Test",
        device_data={"online": True},
        **kwargs,
    )
