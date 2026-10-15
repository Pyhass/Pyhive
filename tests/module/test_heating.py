"""Tests for Climate / HiveHeating."""

# pylint: disable=too-few-public-methods
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.heating import Climate
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_HTTP_OK = 200
_DEFAULT_MIN_TEMP = 5
_DEFAULT_MAX_TEMP = 32
_NATHERMOSTAT_MIN = 7
_NATHERMOSTAT_MAX = 30
_TARGET_TEMP_CELSIUS = 22.0
_BOOST_MINS = "30"
_VALID_BOOST_TEMP = 21
_OUT_OF_RANGE_BOOST_TEMP = 99
_SCHEDULE_MODE = "SCHEDULE"
_MANUAL_MODE = "MANUAL"
_BOOST_MODE = "BOOST"
_TODAY_MIN_TEMP = 18.0
_TODAY_MAX_TEMP = 22.0
_CURRENT_TEMP = 19.0
_TARGET_TEMP_HEAT = 18.5
_TARGET_TEMP_TARGET = 21.0
_ROUNDED_TEMP = 20.2
_RAW_TEMP = 20.25
_BOOST_RESTORE_TARGET = 19.0


def _make_climate(products=None, devices=None, min_max=None):
    """Create a Climate instance with a fully mocked session."""
    session = MagicMock()
    session.data = Map(
        {
            "products": products or {},
            "devices": devices or {},
            "actions": {},
            "minMax": min_max or {},
            "user": {},
        }
    )
    session.config = SessionConfig()
    session.helper = MagicMock()
    session.helper.device_recovered = MagicMock()
    session.helper.error_check = AsyncMock()
    session.helper.get_schedule_nnl = MagicMock(
        return_value={"now": {}, "next": {}, "later": {}}
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
    return Climate(session=session)


def _make_device(hive_id="heat-1", device_id="dev-1", hive_type="heating"):
    """Return a minimal heating Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Hallway",
        hive_type=hive_type,
        ha_type="climate",
        device_id=device_id,
        device_name="Hallway",
        device_data={"online": True},
        ha_name="Hallway",
    )


class TestGetMinMaxTemperature:
    """Tests for get_min_temperature and get_max_temperature."""

    async def test_nathermostat_reads_props(self):
        """nathermostat type reads min/max from product props."""
        climate = _make_climate(
            {
                "heat-1": {
                    "props": {
                        "minHeat": _NATHERMOSTAT_MIN,
                        "maxHeat": _NATHERMOSTAT_MAX,
                    }
                }
            }
        )
        d = _make_device(hive_type="nathermostat")
        assert await climate.get_min_temperature(d) == _NATHERMOSTAT_MIN
        assert await climate.get_max_temperature(d) == _NATHERMOSTAT_MAX

    async def test_other_type_returns_defaults(self):
        """Non-nathermostat type returns hard-coded defaults."""
        climate = _make_climate()
        d = _make_device()
        assert await climate.get_min_temperature(d) == _DEFAULT_MIN_TEMP
        assert await climate.get_max_temperature(d) == _DEFAULT_MAX_TEMP


class TestGetCurrentTemperature:
    """Tests for HiveHeating.get_current_temperature."""

    async def test_happy_path_returns_rounded_float(self):
        """Valid numeric temperature is rounded to one decimal place."""
        climate = _make_climate({"heat-1": {"props": {"temperature": _RAW_TEMP}}})
        result = await climate.get_current_temperature(_make_device())
        assert result == _ROUNDED_TEMP

    async def test_non_numeric_returns_none(self):
        """Non-numeric temperature string returns None."""
        climate = _make_climate({"heat-1": {"props": {"temperature": "N/A"}}})
        assert await climate.get_current_temperature(_make_device()) is None

    async def test_minmax_first_write(self):
        """First temperature reading initialises the minMax entry for the device."""
        climate = _make_climate({"heat-1": {"props": {"temperature": _CURRENT_TEMP}}})
        d = _make_device()
        await climate.get_current_temperature(d)
        assert "heat-1" in climate.session.data.minMax
        assert climate.session.data.minMax["heat-1"]["TodayMin"] == _CURRENT_TEMP


class TestGetTargetTemperature:
    """Tests for HiveHeating.get_target_temperature."""

    async def test_reads_target_key(self):
        """Returns target key when present."""
        climate = _make_climate({"heat-1": {"state": {"target": _TARGET_TEMP_TARGET}}})
        assert (
            await climate.get_target_temperature(_make_device()) == _TARGET_TEMP_TARGET
        )

    async def test_falls_back_to_heat_key(self):
        """Falls back to heat key when target is absent."""
        climate = _make_climate({"heat-1": {"state": {"heat": _TARGET_TEMP_HEAT}}})
        assert await climate.get_target_temperature(_make_device()) == _TARGET_TEMP_HEAT

    async def test_both_absent_returns_none(self):
        """Returns None when neither target nor heat key is present."""
        climate = _make_climate({"heat-1": {"state": {}}})
        assert await climate.get_target_temperature(_make_device()) is None


class TestGetMode:
    """Tests for HiveHeating.get_mode."""

    async def test_schedule_mode(self):
        """SCHEDULE mode is returned as-is."""
        climate = _make_climate({"heat-1": {"state": {"mode": _SCHEDULE_MODE}}})
        result = await climate.get_mode(_make_device())
        assert result == _SCHEDULE_MODE

    async def test_boost_reads_previous_mode(self):
        """BOOST mode resolves to the previous mode stored in props."""
        climate = _make_climate(
            {
                "heat-1": {
                    "state": {"mode": _BOOST_MODE},
                    "props": {"previous": {"mode": _MANUAL_MODE}},
                }
            }
        )
        result = await climate.get_mode(_make_device())
        assert result == _MANUAL_MODE


class TestGetOperationModes:
    """Tests for HiveHeating.get_operation_modes."""

    async def test_returns_three_modes(self):
        """Returns the standard list of three heating operation modes."""
        climate = _make_climate()
        modes = await climate.get_operation_modes()
        assert modes == [_SCHEDULE_MODE, _MANUAL_MODE, "OFF"]


class TestSetTargetTemperature:
    """Tests for HiveHeating.set_target_temperature."""

    async def test_calls_execute_with_target(self):
        """set_target_temperature passes target kwarg to the API."""
        climate = _make_climate({"heat-1": {"type": "heating"}})
        d = _make_device()
        await climate.set_target_temperature(d, _TARGET_TEMP_CELSIUS)
        climate.session.api.set_state.assert_called_once()
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs.get("target") == _TARGET_TEMP_CELSIUS


class TestSetMode:
    """Tests for HiveHeating.set_mode."""

    async def test_calls_execute_with_mode(self):
        """set_mode passes mode kwarg to the API."""
        climate = _make_climate({"heat-1": {"type": "heating"}})
        d = _make_device()
        await climate.set_mode(d, _MANUAL_MODE)
        climate.session.api.set_state.assert_called_once()
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs.get("mode") == _MANUAL_MODE


class TestSetBoostOn:
    """Tests for HiveHeating.set_boost_on."""

    async def test_valid_range_calls_execute(self):
        """Valid minutes and temperature triggers the API call and returns True."""
        climate = _make_climate({"heat-1": {"type": "heating", "props": {}}})
        d = _make_device()
        result = await climate.set_boost_on(d, _BOOST_MINS, _VALID_BOOST_TEMP)
        assert result is True

    async def test_out_of_range_temp_returns_none(self):
        """Temperature above max_temp returns None without calling the API."""
        climate = _make_climate({"heat-1": {"type": "heating"}})
        result = await climate.set_boost_on(
            _make_device(), _BOOST_MINS, _OUT_OF_RANGE_BOOST_TEMP
        )
        assert result is None

    async def test_zero_mins_returns_none(self):
        """Zero minutes returns None without calling the API."""
        climate = _make_climate({"heat-1": {"type": "heating"}})
        result = await climate.set_boost_on(_make_device(), "0", _VALID_BOOST_TEMP)
        assert result is None


class TestSetBoostOff:
    """Tests for HiveHeating.set_boost_off."""

    async def test_offline_returns_false(self):
        """Offline device returns False immediately."""
        climate = _make_climate()
        d = _make_device()
        d.device_data = {"online": False}
        assert await climate.set_boost_off(d) is False

    async def test_not_boosting_returns_false(self):
        """Device not currently boosting returns False."""
        climate = _make_climate({"heat-1": {"state": {"boost": False}}})
        assert await climate.set_boost_off(_make_device()) is False

    async def test_boosting_manual_restores_target(self):
        """Active boost with previous MANUAL mode restores the target temperature."""
        climate = _make_climate(
            {
                "heat-1": {
                    "type": "heating",
                    "state": {"boost": _NATHERMOSTAT_MIN},
                    "props": {
                        "previous": {
                            "mode": _MANUAL_MODE,
                            "target": _BOOST_RESTORE_TARGET,
                        }
                    },
                }
            }
        )
        result = await climate.set_boost_off(_make_device())
        assert result is True
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs.get("target") == _BOOST_RESTORE_TARGET


class TestGetScheduleNowNextLater:
    """Tests for Climate.get_schedule_now_next_later."""

    async def test_online_schedule_mode_calls_helper(self):
        """Online device in SCHEDULE mode returns schedule data."""
        climate = _make_climate(
            {"heat-1": {"state": {"mode": _SCHEDULE_MODE, "schedule": {}}}}
        )
        climate.session.attr.online_offline.return_value = True
        result = await climate.get_schedule_now_next_later(_make_device())
        assert result is not None

    async def test_non_schedule_mode_returns_none(self):
        """Non-SCHEDULE mode returns None."""
        climate = _make_climate({"heat-1": {"state": {"mode": _MANUAL_MODE}}})
        assert await climate.get_schedule_now_next_later(_make_device()) is None


class TestMinMaxTemperature:
    """Tests for Climate.minmax_temperature."""

    async def test_returns_minmax_data(self):
        """Returns minMax entry for the device when present."""
        climate = _make_climate(
            min_max={
                "heat-1": {"TodayMin": _TODAY_MIN_TEMP, "TodayMax": _TODAY_MAX_TEMP}
            }
        )
        result = await climate.minmax_temperature(_make_device())
        assert result["TodayMin"] == _TODAY_MIN_TEMP

    async def test_missing_returns_none(self):
        """Returns None when no minMax entry exists for the device."""
        climate = _make_climate()
        assert await climate.minmax_temperature(_make_device()) is None
