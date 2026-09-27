"""Extended branch-coverage tests for Climate / HiveHeating."""

# pylint: disable=too-few-public-methods
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apyhiveapi.devices.heating import Climate
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_TODAY = str(datetime.date(datetime.now()))
_CURRENT_TEMP = 19.0
_SCHEDULE_MODE = "SCHEDULE"
_BOOST_MINS = 5
_OFF_MODE = "OFF"


def _make_climate(products=None, devices=None, min_max=None):
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
    session.api.set_state = AsyncMock(return_value={"original": 200, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return Climate(session=session)


def _make_device(hive_id="heat-1", device_id="dev-1", hive_type="heating"):
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


class TestGetCurrentTemperature:
    async def test_minmax_today_same_date_updates_min_max(self):
        """When minMax entry exists for today's date, TodayMin/TodayMax are updated."""
        initial_min = _CURRENT_TEMP + 2.0
        initial_max = _CURRENT_TEMP - 2.0
        existing = {
            "TodayMin": initial_min,
            "TodayMax": initial_max,
            "TodayDate": _TODAY,
            "RestartMin": initial_min,
            "RestartMax": initial_max,
        }
        climate = _make_climate(
            products={"heat-1": {"props": {"temperature": _CURRENT_TEMP}}},
            min_max={"heat-1": existing},
        )
        result = await climate.get_current_temperature(_make_device())
        assert result == _CURRENT_TEMP
        entry = climate.session.data.minMax["heat-1"]
        assert entry["TodayMin"] == min(initial_min, _CURRENT_TEMP)
        assert entry["TodayMax"] == max(initial_max, _CURRENT_TEMP)
        assert entry["RestartMin"] == min(initial_min, _CURRENT_TEMP)
        assert entry["RestartMax"] == max(initial_max, _CURRENT_TEMP)

    async def test_minmax_different_date_resets_today(self):
        """When minMax entry exists but TodayDate is stale, today values are reset."""
        existing = {
            "TodayMin": 5.0,
            "TodayMax": 30.0,
            "TodayDate": "2000-01-01",
            "RestartMin": 5.0,
            "RestartMax": 30.0,
        }
        climate = _make_climate(
            products={"heat-1": {"props": {"temperature": _CURRENT_TEMP}}},
            min_max={"heat-1": existing},
        )
        result = await climate.get_current_temperature(_make_device())
        assert result == _CURRENT_TEMP
        entry = climate.session.data.minMax["heat-1"]
        assert entry["TodayMin"] == _CURRENT_TEMP
        assert entry["TodayMax"] == _CURRENT_TEMP
        assert entry["TodayDate"] == _TODAY

    async def test_keyerror_returns_none(self):
        """Missing device.hive_id in products returns None."""
        climate = _make_climate(products={})
        result = await climate.get_current_temperature(_make_device())
        assert result is None


class TestGetTargetTemperature:
    async def test_non_numeric_target_returns_none(self):
        """Non-numeric target temperature string returns None."""
        climate = _make_climate({"heat-1": {"state": {"target": "N/A"}}})
        result = await climate.get_target_temperature(_make_device())
        assert result is None


class TestGetState:
    async def test_current_less_than_target_returns_on(self):
        """When current_temp < target_temp, state resolves to ON."""
        climate = _make_climate(
            {
                "heat-1": {
                    "props": {"temperature": 19.0},
                    "state": {"target": 21.0},
                }
            }
        )
        result = await climate.get_state(_make_device())
        assert result == "ON"

    async def test_current_ge_target_returns_off(self):
        """When current_temp >= target_temp, state resolves to OFF."""
        climate = _make_climate(
            {
                "heat-1": {
                    "props": {"temperature": 21.0},
                    "state": {"target": 19.0},
                }
            }
        )
        result = await climate.get_state(_make_device())
        assert result == "OFF"

    async def test_none_temps_returns_none(self):
        """When temperatures cannot be read, get_state returns None."""
        climate = _make_climate(products={})
        result = await climate.get_state(_make_device())
        assert result is None

    async def test_key_error_in_get_current_temperature_is_caught(self):
        """KeyError from get_current_temperature is caught; get_state returns None."""
        climate = _make_climate(
            {"heat-1": {"state": {"mode": "MANUAL", "target": 20.0}, "props": {}}}
        )
        with patch.object(
            climate, "get_current_temperature", new_callable=AsyncMock
        ) as mock_t:
            mock_t.side_effect = KeyError("missing_key")
            result = await climate.get_state(_make_device())
        assert result is None

    async def test_type_error_in_get_target_temperature_is_caught(self):
        """TypeError from get_target_temperature is caught; get_state returns None."""
        climate = _make_climate(
            {"heat-1": {"state": {"mode": "MANUAL", "target": 20.0}, "props": {}}}
        )
        with patch.object(
            climate, "get_current_temperature", new_callable=AsyncMock
        ) as mock_cur:
            mock_cur.return_value = 19.0
            with patch.object(
                climate, "get_target_temperature", new_callable=AsyncMock
            ) as mock_tgt:
                mock_tgt.side_effect = TypeError("bad type")
                result = await climate.get_state(_make_device())
        assert result is None


class TestGetCurrentOperation:
    async def test_returns_working_state(self):
        """get_current_operation returns the 'working' value from props."""
        climate = _make_climate({"heat-1": {"props": {"working": True}, "state": {}}})
        result = await climate.get_current_operation(_make_device())
        assert result is True


class TestSetBoostOnValidation:
    """set_boost_on input validation must reject bad values with None."""

    async def test_non_numeric_mins_returns_none(self):
        climate = _make_climate(products={"heat-1": {"type": "heating"}})
        result = await climate.set_boost_on(_make_device(), "abc", 20)
        assert result is None

    async def test_non_numeric_temp_returns_none(self):
        climate = _make_climate(products={"heat-1": {"type": "heating"}})
        result = await climate.set_boost_on(_make_device(), "30", "hot")
        assert result is None

    async def test_temp_fraction_above_max_returns_none(self):
        """32.9 exceeds the 32 maximum and must not be truncated past validation."""
        climate = _make_climate(products={"heat-1": {"type": "heating"}})
        result = await climate.set_boost_on(_make_device(), "30", 32.9)
        assert result is None

    async def test_valid_boost_executes_state_change(self):
        climate = _make_climate(products={"heat-1": {"type": "heating"}})
        result = await climate.set_boost_on(_make_device(), "30", 22)
        assert result is True


class TestSetBoostOff:
    async def test_not_in_products_returns_false(self):
        """Device hive_id not present in products returns False."""
        climate = _make_climate(products={})
        result = await climate.set_boost_off(_make_device())
        assert result is False

    async def test_previous_off_mode_restored(self):
        """Previous mode OFF sets mode=OFF and target falls back to 7."""
        climate = _make_climate(
            {
                "heat-1": {
                    "type": "heating",
                    "state": {"boost": _BOOST_MINS},
                    "props": {
                        "previous": {
                            "mode": _OFF_MODE,
                            "target": None,
                        }
                    },
                }
            }
        )
        result = await climate.set_boost_off(_make_device())
        assert result is True
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs.get("mode") == _OFF_MODE
        assert kwargs.get("target") == 7


class TestGetClimate:
    async def test_device_data_not_dict_gets_reset(self):
        """Non-dict device_data is replaced with an empty dict before use."""
        climate = _make_climate(
            products={"heat-1": {"props": {}, "state": {}}},
            devices={"dev-1": {"props": {}, "parent": None}},
        )
        d = _make_device()
        d.device_data = None
        await climate.get_climate(d)
        assert isinstance(d.device_data, dict)

    async def test_offline_device_error_check_called(self):
        """Offline device triggers error_check and status defaults to None values."""
        climate = _make_climate(
            products={"heat-1": {}},
            devices={"dev-1": {}},
        )
        climate.session.attr.online_offline = AsyncMock(return_value=False)
        d = _make_device()
        result = await climate.get_climate(d)
        climate.session.helper.error_check.assert_called_once()
        assert result.status["current_temperature"] is None

    async def test_cache_hit_returns_cached(self):
        """When cached data is available and poll is slow, returns cached device."""
        climate = _make_climate()
        climate.session.should_use_cached_data = MagicMock(return_value=True)
        cached_device = _make_device()
        cached_device.status = {"current_temperature": 20.0}
        climate.session.get_cached_device = MagicMock(return_value=cached_device)
        d = _make_device()
        result = await climate.get_climate(d)
        assert result is cached_device
        climate.session.attr.online_offline.assert_not_called()


class TestGetScheduleNowNextLater:
    async def test_offline_returns_none(self):
        """Offline device returns None regardless of mode."""
        climate = _make_climate(
            {"heat-1": {"state": {"mode": _SCHEDULE_MODE, "schedule": {}}}}
        )
        climate.session.attr.online_offline = AsyncMock(return_value=False)
        result = await climate.get_schedule_now_next_later(_make_device())
        assert result is None


# ---------------------------------------------------------------------------
# get_mode — BOOST path with missing props.previous must not log error
# ---------------------------------------------------------------------------


class TestGetModeBoostMissingPrevious:
    """get_mode BOOST path must use safe access, not bare dict that logs a spurious error."""

    async def test_boost_missing_previous_returns_none_without_error_log(self):
        """When mode=BOOST and props has no previous, get_mode returns None without error log."""
        climate = _make_climate({"heat-1": {"state": {"mode": "BOOST"}, "props": {}}})
        d = _make_device()
        with patch("apyhiveapi.devices.heating._LOGGER") as mock_log:
            result = await climate.get_mode(d)
        assert result is None
        mock_log.error.assert_not_called()

    async def test_boost_with_previous_mode_returns_mapped_value(self):
        """When mode=BOOST and props.previous.mode exists, returns the mapped HA value."""
        from apyhiveapi.helper.const import HIVETOHA

        climate = _make_climate(
            {
                "heat-1": {
                    "state": {"mode": "BOOST"},
                    "props": {"previous": {"mode": "MANUAL"}},
                }
            }
        )
        d = _make_device()
        result = await climate.get_mode(d)
        expected = HIVETOHA["Heating"].get("MANUAL", "MANUAL")
        assert result == expected


# ---------------------------------------------------------------------------
# set_boost_off — must return False when prev_mode is None (not send mode=None to API)
# ---------------------------------------------------------------------------


class TestSetBoostOffNullPrevMode:
    """set_boost_off returns False (not an API call) when prev_mode is None."""

    async def test_set_boost_off_returns_false_when_prev_mode_missing(self):
        """set_boost_off returns False and skips _execute_state_change when prev mode absent."""
        from apyhiveapi.devices.heating import HiveHeating

        class StubHeating(HiveHeating):
            """Concrete stub for testing."""

        h = StubHeating()
        h.session = MagicMock()
        h.session.data.products = {
            "h1": {
                "state": {"mode": "BOOST"},
                "props": {},
            }
        }
        h._execute_state_change = AsyncMock(return_value=True)
        h.get_boost_status = AsyncMock(return_value="ON")

        d = Device(
            hive_id="h1",
            hive_name="T",
            hive_type="heating",
            ha_type="climate",
            device_id="d1",
            device_name="T",
            device_data={"online": True},
            ha_name="Heating",
        )
        result = await h.set_boost_off(d)
        assert result is False
        h._execute_state_change.assert_not_called()


# ===========================================================================
# Migrated from test_remaining_branches.py
# ===========================================================================


class TestHeatingGetStateKeyError:
    """Lines 206-207: KeyError/TypeError branch in get_state."""

    async def test_get_state_key_error_returns_none(self):
        """Missing product entry causes get_current_temperature to return None,
        leaving final as None without raising."""
        # products dict is empty — device.hive_id not found → both temp helpers
        # return None → the if branch is skipped → final stays None
        climate = _make_climate(products={})
        d = _make_device()
        result = await climate.get_state(d)
        assert result is None


class TestHeatingGetHeatOnDemand:
    """Line 231: get_heat_on_demand happy path."""

    async def test_get_heat_on_demand_returns_value(self):
        """Returns the nested autoBoost.active value from products."""
        climate = _make_climate({"heat-1": {"props": {"autoBoost": {"active": True}}}})
        result = await climate.get_heat_on_demand(_make_device())
        assert result is True

    async def test_get_heat_on_demand_returns_none_when_missing(self):
        """Returns None when the nested path does not exist."""
        climate = _make_climate({"heat-1": {"props": {}}})
        result = await climate.get_heat_on_demand(_make_device())
        assert result is None


class TestHeatingSetHeatOnDemand:
    """Lines 337-342: set_heat_on_demand calls _execute_state_change with autoBoost kwarg."""

    async def test_set_heat_on_demand_enabled(self):
        """set_heat_on_demand passes autoBoost='ENABLED' to the API."""
        climate = _make_climate({"heat-1": {"type": "heating"}})
        result = await climate.set_heat_on_demand(_make_device(), "ENABLED")
        assert result is True
        climate.session.api.set_state.assert_called_once()
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs.get("autoBoost") == "ENABLED"

    async def test_set_heat_on_demand_disabled(self):
        """set_heat_on_demand passes autoBoost='DISABLED' to the API."""
        climate = _make_climate({"heat-1": {"type": "heating"}})
        result = await climate.set_heat_on_demand(_make_device(), "DISABLED")
        assert result is True
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs.get("autoBoost") == "DISABLED"


class TestHeatingGetScheduleNNLKeyError:
    """Lines 438-439: KeyError in get_schedule_now_next_later."""

    async def test_missing_schedule_key_returns_none(self):
        """Product with state but no 'schedule' key causes KeyError → returns None."""
        climate = _make_climate(
            {"heat-1": {"state": {"mode": "SCHEDULE"}}}
            # no 'schedule' key inside state
        )
        # Override get_mode to return SCHEDULE directly so the if-branch is entered
        climate.session.helper.get_schedule_nnl.side_effect = KeyError("schedule")
        # get_mode will read data["state"]["mode"] == "SCHEDULE" → enters the try block
        # data["state"]["schedule"] raises KeyError → caught, returns None
        result = await climate.get_schedule_now_next_later(_make_device())
        assert result is None

    async def test_schedule_key_error_caught_not_raised(self):
        """A KeyError inside the try block does not propagate to the caller."""
        climate = _make_climate({"heat-1": {"state": {"mode": "SCHEDULE"}}})
        # Accessing data["state"]["schedule"] will raise KeyError (key absent)
        try:
            result = await climate.get_schedule_now_next_later(_make_device())
        except KeyError:
            pytest.fail(
                "KeyError should have been caught inside get_schedule_now_next_later"
            )
        assert result is None


class TestHeatingSetBoostOffScheduleMode:
    """Lines 321->325: prev_mode not in ('MANUAL','OFF') — target kwarg not added."""

    async def test_schedule_mode_no_target_kwarg(self):
        """SCHEDULE as previous mode does not add a target kwarg."""
        climate = _make_climate(
            {
                "heat-1": {
                    "type": "heating",
                    "state": {"boost": 5},
                    "props": {"previous": {"mode": "SCHEDULE"}},
                }
            }
        )
        result = await climate.set_boost_off(_make_device())
        assert result is True
        _, kwargs = climate.session.api.set_state.call_args
        assert "target" not in kwargs
        assert kwargs.get("mode") == "SCHEDULE"


class TestHeatingGetClimateCacheMiss:
    """Lines 371->377: cache enabled but cached device is None → normal execution."""

    async def test_cached_none_falls_through_to_normal_path(self):
        """should_use_cached_data=True but get_cached_device=None → normal update."""
        climate = _make_climate(
            {
                "heat-1": {
                    "state": {"mode": "MANUAL", "target": 20.0},
                    "props": {"temperature": 19.0},
                }
            },
            devices={"dev-1": {"state": {}, "props": {}}},
        )
        climate.session.should_use_cached_data.return_value = True
        climate.session.get_cached_device.return_value = None
        result = await climate.get_climate(_make_device())
        assert result is not None
        climate.session.attr.online_offline.assert_called_once()
