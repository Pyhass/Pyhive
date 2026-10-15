"""Tests for session polling behaviour, HiveHub sensor status, and Hive lifecycle."""

# pylint: disable=protected-access
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi import Hive
from apyhiveapi.devices.hub import HiveHub
from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.helper.map import Map


async def test_force_update_polls_when_idle():
    """force_update() calls _poll_devices and returns its result when no poll is running."""
    async with Hive(
        username="test@example.com",
        password="pass",  # pragma: allowlist secret
    ) as hive:
        hive._poll_devices = AsyncMock(return_value=True)
        result = await hive.force_update()

    assert result is True
    hive._poll_devices.assert_called_once()


async def test_force_update_skips_when_locked():
    """force_update() returns False without polling when the update lock is already held."""
    async with Hive(
        username="test@example.com",
        password="pass",  # pragma: allowlist secret
    ) as hive:
        hive._poll_devices = AsyncMock(return_value=True)

        async with hive.update_lock:
            result = await hive.force_update()

    assert result is False
    hive._poll_devices.assert_not_called()


# ---------------------------------------------------------------------------
# Shared fixtures for HiveHub sensor tests
# ---------------------------------------------------------------------------

SMOKE_PRODUCTS = {
    "hub-1": {
        "props": {
            "sensors": {
                "SMOKE_CO": {"active": True},
                "DOG_BARK": {"active": False},
                "GLASS_BREAK": {"active": True},
            }
        }
    }
}


def _make_hub_handler(products):
    """Build a HiveHub with a mocked session."""
    session = MagicMock()
    session.data = Map(
        {"products": products, "devices": {}, "actions": {}, "minMax": {}, "user": {}}
    )
    return HiveHub(session=session)


def _make_hub_device(hive_id="hub-1"):
    """Return a minimal sense Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Hub",
        hive_type="sense",
        ha_type="binary_sensor",
        device_id="hub-1",
        device_name="Hub",
        device_data={"online": True},
    )


class TestHiveHubSensorStatus:
    """Tests for HiveHub smoke, dog-bark and glass-break sensor status methods."""

    async def test_smoke_active_true_returns_1(self):
        """get_smoke_status returns 1 when SMOKE_CO active is True."""
        hub = _make_hub_handler(SMOKE_PRODUCTS)
        assert await hub.get_smoke_status(_make_hub_device()) == 1

    async def test_smoke_active_false_returns_0(self):
        """get_smoke_status returns 0 when SMOKE_CO active is False."""
        prods = {"hub-1": {"props": {"sensors": {"SMOKE_CO": {"active": False}}}}}
        hub = _make_hub_handler(prods)
        assert await hub.get_smoke_status(_make_hub_device()) == 0

    async def test_smoke_missing_returns_none(self):
        """get_smoke_status returns None when the product key is absent."""
        hub = _make_hub_handler({})
        assert await hub.get_smoke_status(_make_hub_device()) is None

    async def test_dog_bark_false_returns_0(self):
        """get_dog_bark_status returns 0 when DOG_BARK active is False."""
        hub = _make_hub_handler(SMOKE_PRODUCTS)
        assert await hub.get_dog_bark_status(_make_hub_device()) == 0

    async def test_dog_bark_missing_returns_none(self):
        """get_dog_bark_status returns None when the product key is absent."""
        hub = _make_hub_handler({})
        assert await hub.get_dog_bark_status(_make_hub_device()) is None

    async def test_glass_break_active_true_returns_1(self):
        """get_glass_break_status returns 1 when GLASS_BREAK active is True."""
        hub = _make_hub_handler(SMOKE_PRODUCTS)
        assert await hub.get_glass_break_status(_make_hub_device()) == 1

    async def test_glass_break_missing_returns_none(self):
        """get_glass_break_status returns None when the product key is absent."""
        hub = _make_hub_handler({})
        assert await hub.get_glass_break_status(_make_hub_device()) is None


class TestHiveHubHolidayMode:
    """Tests for HiveHub holiday mode get/set/cancel methods."""

    def _make_hub(self, resp):
        session = MagicMock()
        session.hive_refresh_tokens = AsyncMock()
        session.api = MagicMock()
        session.api.get_holiday_mode = AsyncMock(return_value=resp)
        session.api.set_holiday_mode = AsyncMock(return_value=resp)
        session.api.cancel_holiday_mode = AsyncMock(return_value=resp)
        return HiveHub(session=session)

    async def test_get_holiday_mode_returns_parsed_on_200(self):
        payload = {
            "active": False,
            "enabled": False,
            "start": 1,
            "end": 2,
            "temperature": 12,
        }
        hub = self._make_hub({"original": 200, "parsed": payload})
        assert await hub.get_holiday_mode() == payload

    async def test_get_holiday_mode_returns_none_on_failure(self):
        hub = self._make_hub(
            {"original": 400, "parsed": {"error": "MALFORMED_REQUEST"}}
        )
        assert await hub.get_holiday_mode() is None

    async def test_set_holiday_mode_returns_true_on_200(self):
        hub = self._make_hub({"original": 200, "parsed": {}})
        start = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)
        assert await hub.set_holiday_mode(start, end, 12) is True
        hub.session.api.set_holiday_mode.assert_awaited_once_with(
            int(start.timestamp() * 1000), int(end.timestamp() * 1000), 12
        )

    async def test_set_holiday_mode_returns_false_on_failure(self):
        hub = self._make_hub({"original": 400, "parsed": {}})
        start = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)
        assert await hub.set_holiday_mode(start, end, 12) is False

    async def test_cancel_holiday_mode_returns_true_on_200(self):
        hub = self._make_hub({"original": 200, "parsed": {"set": True}})
        assert await hub.cancel_holiday_mode() is True

    async def test_cancel_holiday_mode_returns_false_on_failure(self):
        hub = self._make_hub({"original": 400, "parsed": {}})
        assert await hub.cancel_holiday_mode() is False


class TestHiveLifecycle:
    """Tests for Hive context manager."""

    async def test_context_manager_aenter_returns_self(self):
        """__aenter__ returns the Hive instance itself."""
        async with Hive(
            username="test@example.com",
            password="pass",  # pragma: allowlist secret
        ) as hive:
            assert hive is not None

    async def test_close_calls_websession_close(self):
        """__aexit__ closes the lazily created aiohttp websession."""
        async with Hive(
            username="test@example.com",
            password="pass",  # pragma: allowlist secret
        ) as hive:
            # The websession is created lazily, on first use inside the loop.
            assert hive.api.websession is None
            ws = hive.api._get_websession()
        # After context exit the session should be closed
        assert ws.closed
