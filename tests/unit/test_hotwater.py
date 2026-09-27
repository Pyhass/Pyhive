"""Extended branch-coverage tests for WaterHeater / HiveHotwater."""

# pylint: disable=too-few-public-methods
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.hotwater import WaterHeater
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_SCHEDULE_MODE = "SCHEDULE"
_ON_MODE = "ON"
_OFF_MODE = "OFF"
_BOOST_MODE = "BOOST"


def _make_hotwater(products=None, devices=None):
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
        return_value={"now": {"value": {"status": _ON_MODE}}, "next": {}, "later": {}}
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
    return WaterHeater(session=session)


def _make_device(hive_id="hw-1", device_id="dev-1"):
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
    async def test_boost_mode_reads_previous(self):
        """BOOST state resolves to the previous mode stored in props."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "state": {"mode": _BOOST_MODE},
                    "props": {"previous": {"mode": _ON_MODE}},
                }
            }
        )
        result = await hw.get_mode(_make_device())
        assert result == _ON_MODE


class TestGetState:
    async def test_schedule_mode_boost_off_reads_schedule(self):
        """SCHEDULE mode with boost OFF reads state from schedule nnl."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "state": {
                        "mode": _SCHEDULE_MODE,
                        "status": _OFF_MODE,
                        "boost": False,
                        "schedule": {},
                    }
                }
            }
        )
        result = await hw.get_state(_make_device())
        assert result is not None

    async def test_non_schedule_state_mapped(self):
        """Direct ON mode/status maps through HIVETOHA without schedule lookup."""
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


class TestGetWaterHeater:
    async def test_cache_hit_returns_cached(self):
        """Cached device is returned immediately when poll is slow/busy."""
        hw = _make_hotwater()
        hw.session.should_use_cached_data = MagicMock(return_value=True)
        cached_device = _make_device()
        cached_device.status = {"current_operation": _SCHEDULE_MODE}
        hw.session.get_cached_device = MagicMock(return_value=cached_device)
        d = _make_device()
        result = await hw.get_water_heater(d)
        assert result is cached_device
        hw.session.attr.online_offline.assert_not_called()

    async def test_device_data_not_dict_gets_reset(self):
        """Non-dict device_data is replaced with an empty dict before use."""
        hw = _make_hotwater(
            products={"hw-1": {"state": {"mode": _SCHEDULE_MODE}}},
            devices={"dev-1": {"props": {}, "parent": None}},
        )
        d = _make_device()
        d.device_data = None
        await hw.get_water_heater(d)
        assert isinstance(d.device_data, dict)

    async def test_offline_device_calls_error_check(self):
        """Offline device triggers error_check and status defaults to None."""
        hw = _make_hotwater(
            products={"hw-1": {}},
            devices={"dev-1": {}},
        )
        hw.session.attr.online_offline = AsyncMock(return_value=False)
        d = _make_device()
        result = await hw.get_water_heater(d)
        hw.session.helper.error_check.assert_called_once()
        assert result.status["current_operation"] is None


class TestGetScheduleNowNextLater:
    async def test_schedule_mode_returns_nnl(self):
        """SCHEDULE mode with schedule data returns now/next/later dict."""
        hw = _make_hotwater(
            {"hw-1": {"state": {"mode": _SCHEDULE_MODE, "schedule": {"data": []}}}}
        )
        result = await hw.get_schedule_now_next_later(_make_device())
        assert result is not None
        assert "now" in result

    async def test_non_schedule_mode_returns_none(self):
        """Non-SCHEDULE mode returns None."""
        hw = _make_hotwater({"hw-1": {"state": {"mode": _ON_MODE}}})
        result = await hw.get_schedule_now_next_later(_make_device())
        assert result is None


# ---------------------------------------------------------------------------
# get_mode — BOOST path with missing props.previous must not log error
# ---------------------------------------------------------------------------


class TestHotwaterGetModeBoostMissingPrevious:
    """get_mode BOOST path must use safe access, not bare dict that logs a spurious error."""

    async def test_boost_missing_previous_returns_off_without_error_log(  # noqa: E501
        self,
    ):
        """When mode=BOOST and props has no previous, get_mode returns 'OFF' without error log.

        The hotwater HIVETOHA mapping maps None→'OFF', so missing previous
        resolves safely instead of throwing a swallowed KeyError.
        """
        from unittest.mock import patch

        hw = _make_hotwater({"hw-1": {"state": {"mode": "BOOST"}, "props": {}}})
        d = _make_device()
        with patch("apyhiveapi.devices.hotwater._LOGGER") as mock_log:
            result = await hw.get_mode(d)
        assert result == "OFF"
        mock_log.error.assert_not_called()


# ---------------------------------------------------------------------------
# set_boost_off — must return False when prev_mode is None (not send mode=None)
# ---------------------------------------------------------------------------


class TestHotwaterSetBoostOffNullPrevMode:
    """HiveHotwater.set_boost_off returns False when prev_mode is None."""

    async def test_set_boost_off_returns_false_when_prev_mode_missing(self):
        """set_boost_off returns False and does not call API when prev mode is absent."""
        from apyhiveapi.devices.hotwater import HiveHotwater

        class StubHotwater(HiveHotwater):
            """Concrete stub for testing."""

        h = StubHotwater()
        h.session = MagicMock()
        h.session.data.products = {"h1": {"state": {"mode": "BOOST"}, "props": {}}}
        h._execute_state_change = AsyncMock(return_value=True)
        h.get_boost_status = AsyncMock(return_value="ON")

        d = Device(
            hive_id="h1",
            hive_name="T",
            hive_type="hotwater",
            ha_type="water_heater",
            device_id="d1",
            device_name="T",
            device_data={"online": True},
            ha_name="Hotwater",
        )
        result = await h.set_boost_off(d)
        assert result is False
        h._execute_state_change.assert_not_called()


class TestHotwaterGetStateScheduleGuard:
    """get_state handles empty schedule NNL without KeyError."""

    async def test_get_state_schedule_guard_empty_nnl(self):
        """get_state does not crash when get_schedule_nnl returns empty dict."""
        from apyhiveapi.devices.hotwater import HiveHotwater

        class StubHotwater(HiveHotwater):
            pass

        h = StubHotwater()
        h.session = MagicMock()
        h.session.data.products = {
            "h1": {
                "state": {"status": "ON", "mode": "SCHEDULE", "schedule": {}},
                "props": {},
            }
        }
        h.session.helper.get_schedule_nnl = MagicMock(return_value={})
        h.get_mode = AsyncMock(return_value="SCHEDULE")
        h.get_boost_status = AsyncMock(return_value="OFF")

        d = Device(
            hive_id="h1",
            hive_name="T",
            hive_type="hotwater",
            ha_type="water_heater",
            device_id="d1",
            device_name="T",
            device_data={"online": True},
            ha_name="Hotwater",
        )
        result = await h.get_state(d)
        assert result is None or isinstance(result, str)


# ===========================================================================
# Migrated from test_remaining_branches.py
# ===========================================================================


class TestHotwaterGetModeKeyError:
    """Lines 43-44: KeyError in get_mode."""

    async def test_get_mode_missing_state_returns_none(self):
        """Product with no 'state' key causes KeyError → final stays None."""
        hw = _make_hotwater({"hw-1": {}})
        result = await hw.get_mode(_make_device())
        assert result is None


class TestHotwaterGetStateKeyError:
    """Lines 83-84: KeyError in get_state."""

    async def test_get_state_missing_status_key_returns_none(self):
        """Product 'state' dict missing 'status' key triggers KeyError → None."""
        hw = _make_hotwater({"hw-1": {"state": {"mode": "MANUAL"}}})
        # 'status' key is absent from state → KeyError on data["state"]["status"]
        result = await hw.get_state(_make_device())
        assert result is None

    async def test_get_state_missing_schedule_in_schedule_mode_returns_none(self):
        """SCHEDULE mode with no 'schedule' key in state causes KeyError → None."""
        hw = _make_hotwater(
            {
                "hw-1": {
                    "state": {
                        "mode": "SCHEDULE",
                        "status": "ON",
                        "boost": False,
                        # no 'schedule' key
                    }
                }
            }
        )
        result = await hw.get_state(_make_device())
        assert result is None


class TestHotwaterScheduleNNLNone:
    """Lines 225->227: get_schedule_now_next_later returns None when schedule is absent."""

    async def test_schedule_none_when_no_schedule_in_state(self):
        """SCHEDULE mode product without 'schedule' key → _get_product_state returns None → None."""
        hw = _make_hotwater({"hw-1": {"state": {"mode": "SCHEDULE"}}})
        # _get_product_state(device, "state", "schedule") → None (key absent)
        result = await hw.get_schedule_now_next_later(_make_device())
        assert result is None


class TestHotwaterGetWaterHeaterCacheMiss:
    """Lines 173->180: cache enabled but cached is None → continues with network call."""

    async def test_cached_none_falls_through(self):
        hw = _make_hotwater(
            {"hw-1": {"state": {"mode": "ON"}, "props": {}}},
            devices={"dev-1": {"state": {}, "props": {}}},
        )
        hw.session.should_use_cached_data.return_value = True
        hw.session.get_cached_device.return_value = None
        result = await hw.get_water_heater(_make_device())
        assert result is not None
        hw.session.attr.online_offline.assert_called_once()
