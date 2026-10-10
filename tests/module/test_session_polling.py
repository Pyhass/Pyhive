"""Tests for PollingMixin.update_data rate-limiting behaviour."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock

from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map
from apyhiveapi.session.polling import PollingMixin

_FAR_PAST = timedelta(seconds=9999)


def _make_stub(*, stale=True):
    """Return a PollingMixin stub whose last_update is controllably old or fresh."""

    class StubPolling(PollingMixin):
        """Concrete subclass used only for testing."""

    p = StubPolling()
    p.config = SessionConfig()
    p.config.last_update = datetime.now() - _FAR_PAST if stale else datetime.now()
    p.data = Map(
        {"products": {}, "devices": {}, "actions": {}, "minMax": {}, "user": {}}
    )
    p.tokens = None
    p.entity_cache = {}
    p.update_lock = asyncio.Lock()
    p._update_task = None
    p._last_poll_slow = False
    p._slow_poll_threshold = 3
    p._poll_devices = AsyncMock(return_value=True)
    return p


def _make_device():
    return Device(
        hive_id="prod-1",
        hive_name="Test",
        hive_type="heating",
        ha_type="climate",
        device_id="dev-1",
        device_name="Test",
        device_data={"online": True},
    )


class TestUpdateData:
    """Tests for PollingMixin.update_data."""

    async def test_stale_last_update_triggers_poll_returns_true(self):
        """update_data polls and returns True when last_update is older than scan_interval."""
        p = _make_stub(stale=True)
        result = await p.update_data(_make_device())
        assert result is True
        p._poll_devices.assert_called_once()

    async def test_fresh_last_update_skips_poll_returns_false(self):
        """update_data skips the poll and returns False within scan_interval."""
        p = _make_stub(stale=False)
        result = await p.update_data(_make_device())
        assert result is False
        p._poll_devices.assert_not_called()

    async def test_lock_held_by_other_returns_false_without_polling(self):
        """update_data returns False immediately when another task holds the update lock."""
        p = _make_stub(stale=True)
        await p.update_lock.acquire()
        p._update_task = None  # lock is held but not by a recognised update task
        try:
            result = await p.update_data(_make_device())
        finally:
            p.update_lock.release()
        assert result is False
        p._poll_devices.assert_not_called()

    async def test_update_task_cleared_after_successful_poll(self):
        """_update_task is reset to None once update_data completes."""
        p = _make_stub(stale=True)
        await p.update_data(_make_device())
        assert p._update_task is None

    async def test_failed_poll_returns_false(self):
        """update_data returns False when _poll_devices itself returns False."""
        p = _make_stub(stale=True)
        p._poll_devices = AsyncMock(return_value=False)
        result = await p.update_data(_make_device())
        assert result is False
