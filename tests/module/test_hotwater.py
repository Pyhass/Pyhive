"""Tests for WaterHeater / HiveHotwater."""

# pylint: disable=too-few-public-methods
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.hotwater import WaterHeater
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_HTTP_OK = 200
_BOOST_MINS = 30
_SCHEDULE_MODE = "SCHEDULE"
_ON_MODE = "ON"
_OFF_MODE = "OFF"
_BOOST_MODE = "BOOST"


def _make_hotwater(products=None, devices=None):
    """Create a WaterHeater instance with a fully mocked session."""
    session = MagicMock()
    session.data = Map(
        {
            "products": products or {},
            "devices": devices or {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    session.config = SessionConfig()
    session.helper = MagicMock()
    session.helper.device_recovered = MagicMock()
    session.helper.error_check = AsyncMock()
    session.helper.get_schedule_nnl = MagicMock(
        return_value={"now": {"value": {"status": "ON"}}, "next": {}, "later": {}}
    )
    session.attr = MagicMock()
    session.attr.online_offline = AsyncMock(return_value=True)
    session.attr.state_attributes = AsyncMock(return_value={})
    session.api = MagicMock()
    session.api.set_state = AsyncMock(return_value={"original": _HTTP_OK, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return WaterHeater(session=session)


def _make_device(hive_id="hw-1", device_id="dev-1"):
    """Return a minimal hot water Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Hot Water",
        hive_type="hotwater",
        ha_type="water_heater",
        device_id=device_id,
        device_name="Hot Water",
        device_data={"online": True},
        ha_name="Hot Water",
    )


class TestGetMode:
    """Tests for HiveHotwater.get_mode."""

    async def test_schedule_mode(self):
        """SCHEDULE mode is returned as-is (not in HIVETOHA Hotwater map)."""
        hw = _make_hotwater({"hw-1": {"state": {"mode": _SCHEDULE_MODE}}})
        assert await hw.get_mode(_make_device()) == _SCHEDULE_MODE

    async def test_boost_reads_previous(self):
        """BOOST mode resolves to the previous mode stored in props."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "state": {"mode": _BOOST_MODE},
                    "props": {"previous": {"mode": _ON_MODE}},
                }
            }
        )
        assert await hw.get_mode(_make_device()) == _ON_MODE


class TestGetState:
    """Tests for HiveHotwater.get_state."""

    async def test_direct_on(self):
        """ON mode/status returns a non-None state value."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "state": {
                        "mode": _ON_MODE,
                        "status": _ON_MODE,
                        "schedule": {},
                    }
                }
            }
        )
        result = await hw.get_state(_make_device())
        assert result is not None

    async def test_schedule_with_boost_on_returns_on(self):
        """SCHEDULE mode with active boost overrides schedule state to ON."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "state": {
                        "mode": _SCHEDULE_MODE,
                        "status": _OFF_MODE,
                        "boost": _BOOST_MINS,
                        "schedule": {},
                    }
                }
            }
        )
        result = await hw.get_state(_make_device())
        assert result is not None


class TestGetOperationModes:
    """Tests for HiveHotwater.get_operation_modes."""

    async def test_returns_three_modes(self):
        """Returns the standard list of three hot water operation modes."""
        hw = _make_hotwater()
        assert await hw.get_operation_modes() == [_SCHEDULE_MODE, _ON_MODE, _OFF_MODE]


class TestSetMode:
    """Tests for HiveHotwater.set_mode."""

    async def test_calls_execute_with_mode(self):
        """set_mode passes mode kwarg to the API."""
        hw = _make_hotwater({"hw-1": {"type": "hotwater"}})
        await hw.set_mode(_make_device(), _ON_MODE)
        hw.session.api.set_state.assert_called_once()
        _, kwargs = hw.session.api.set_state.call_args
        assert kwargs.get("mode") == _ON_MODE


class TestSetBoostOn:
    """Tests for HiveHotwater.set_boost_on."""

    async def test_valid_mins_calls_execute(self):
        """Positive minutes value triggers the API call and returns True."""
        hw = _make_hotwater({"hw-1": {"type": "hotwater"}})
        result = await hw.set_boost_on(_make_device(), _BOOST_MINS)
        assert result is True

    async def test_zero_mins_returns_false(self):
        """Zero minutes returns False without calling the API."""
        hw = _make_hotwater()
        assert await hw.set_boost_on(_make_device(), 0) is False


class TestSetBoostOff:
    """Tests for HiveHotwater.set_boost_off."""

    async def test_not_in_products_returns_false(self):
        """Device not found in products returns False immediately."""
        hw = _make_hotwater()
        assert await hw.set_boost_off(_make_device()) is False

    async def test_not_boosting_returns_false(self):
        """Device not actively boosting returns False."""
        hw = _make_hotwater({"hw-1": {"state": {"boost": False}}})
        assert await hw.set_boost_off(_make_device()) is False

    async def test_boosting_calls_execute_with_prev_mode(self):
        """Active boost restores the previous mode via the API."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "type": "hotwater",
                    "state": {"boost": _BOOST_MINS},
                    "props": {"previous": {"mode": _SCHEDULE_MODE}},
                }
            }
        )
        result = await hw.set_boost_off(_make_device())
        assert result is True
        _, kwargs = hw.session.api.set_state.call_args
        assert kwargs.get("mode") == _SCHEDULE_MODE


class TestGetScheduleNowNextLater:
    """Tests for WaterHeater.get_schedule_now_next_later."""

    async def test_non_schedule_returns_none(self):
        """Non-SCHEDULE mode returns None."""
        hw = _make_hotwater({"hw-1": {"state": {"mode": _ON_MODE}}})
        assert await hw.get_schedule_now_next_later(_make_device()) is None
