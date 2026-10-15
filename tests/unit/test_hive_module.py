"""Unit tests for hive.py module-level functions and the Hive class."""

# pylint: disable=protected-access,too-few-public-methods

from unittest.mock import AsyncMock

import pytest
from apyhiveapi.hive import Hive


class TestHiveInit:
    """Tests for Hive.__init__ device module composition."""

    async def test_initializes_action(self):
        from apyhiveapi.devices.action import HiveAction

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.action, HiveAction)

    async def test_initializes_heating(self):
        from apyhiveapi.devices.heating import Climate

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.heating, Climate)

    async def test_initializes_hotwater(self):
        from apyhiveapi.devices.hotwater import WaterHeater

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.hotwater, WaterHeater)

    async def test_initializes_hub(self):
        from apyhiveapi.devices.hub import HiveHub

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.hub, HiveHub)

    async def test_initializes_light(self):
        from apyhiveapi.devices.light import Light

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.light, Light)

    async def test_initializes_switch(self):
        from apyhiveapi.devices.plug import Switch

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.switch, Switch)

    async def test_initializes_sensor(self):
        from apyhiveapi.devices.sensor import Sensor

        async with Hive(username="use@file.com", password="") as hive:
            assert isinstance(hive.sensor, Sensor)

    async def test_session_is_self(self):
        async with Hive(username="use@file.com", password="") as hive:
            assert hive.session is hive


class TestForceUpdate:
    """Tests for Hive.force_update."""

    async def test_lock_free_calls_poll_devices(self):
        async with Hive(username="use@file.com", password="") as hive:
            hive._poll_devices = AsyncMock(return_value=True)
            result = await hive.force_update()
        assert result is True
        hive._poll_devices.assert_awaited_once()

    async def test_lock_free_returns_poll_result(self):
        async with Hive(username="use@file.com", password="") as hive:
            hive._poll_devices = AsyncMock(return_value=False)
            result = await hive.force_update()
        assert result is False

    async def test_lock_held_returns_false(self):
        async with Hive(username="use@file.com", password="") as hive:
            hive._poll_devices = AsyncMock(return_value=True)
            await hive.update_lock.acquire()
            try:
                result = await hive.force_update()
            finally:
                hive.update_lock.release()
        assert result is False
        hive._poll_devices.assert_not_awaited()

    async def test_update_task_cleared_after_poll(self):
        async with Hive(username="use@file.com", password="") as hive:
            hive._poll_devices = AsyncMock(return_value=True)
            await hive.force_update()
            assert hive._update_task is None

    async def test_update_task_cleared_even_on_exception(self):
        async with Hive(username="use@file.com", password="") as hive:
            hive._poll_devices = AsyncMock(side_effect=RuntimeError("poll failed"))
            with pytest.raises(RuntimeError, match="poll failed"):
                await hive.force_update()
            assert hive._update_task is None
