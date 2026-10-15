"""Extended branch-coverage tests for Light (devices/light.py)."""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.light import Light
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map


def _make_session(products=None, devices=None):
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
    return session


def _make_device(
    hive_id="light-1",
    device_id="dev-1",
    hive_type="warmwhitelight",
    ha_type="light",
):
    return Device(
        hive_id=hive_id,
        hive_name="Living Room Light",
        hive_type=hive_type,
        ha_type=ha_type,
        device_id=device_id,
        device_name="Living Room Light",
        device_data={"online": True},
        ha_name="Living Room",
    )


# Minimal product data sufficient for get_state / get_brightness
_WARMWHITE_PRODUCT = {
    "type": "warmwhitelight",
    "state": {"status": "ON", "brightness": 100},
    "props": {"online": True},
}

_TUNEABLE_PRODUCT = {
    "type": "tuneablelight",
    "state": {
        "status": "ON",
        "brightness": 80,
        "colourTemperature": 4000,
    },
    "props": {
        "online": True,
        "colourTemperature": {"min": 2700, "max": 6500},
    },
}

_COLOUR_TUNEABLE_PRODUCT = {
    "type": "colourtuneablelight",
    "state": {
        "status": "ON",
        "brightness": 60,
        "colourTemperature": 4000,
        "colourMode": "COLOUR",
        "hue": 120,
        "saturation": 100,
        "value": 100,
    },
    "props": {
        "online": True,
        "colourTemperature": {"min": 2700, "max": 6500},
    },
}

_COLOUR_TUNEABLE_WHITE_PRODUCT = {
    "type": "colourtuneablelight",
    "state": {
        "status": "ON",
        "brightness": 60,
        "colourTemperature": 4000,
        "colourMode": "WHITE",
    },
    "props": {
        "online": True,
        "colourTemperature": {"min": 2700, "max": 6500},
    },
}


class TestGetLight:
    """Tests for Light.get_light covering previously uncovered branches."""

    async def test_cache_hit_returns_cached_device(self):
        """Lines 141-147: should_use_cached_data True + cache hit returns cached."""
        session = _make_session()
        cached_device = _make_device()
        session.should_use_cached_data = MagicMock(return_value=True)
        session.get_cached_device = MagicMock(return_value=cached_device)

        light = Light(session=session)
        device = _make_device()
        result = await light.get_light(device)

        assert result is cached_device
        session.attr.online_offline.assert_not_called()

    async def test_device_data_not_dict_gets_initialized(self):
        """Line 149: non-dict device_data is replaced with an empty dict."""
        device_id = "dev-1"
        hive_id = "light-1"
        products = {hive_id: _WARMWHITE_PRODUCT}
        devices = {device_id: {"props": {"online": True}, "parent": None}}
        session = _make_session(products=products, devices=devices)

        light = Light(session=session)
        device = _make_device(hive_id=hive_id, device_id=device_id)
        device.device_data = "not-a-dict"

        result = await light.get_light(device)

        # After the branch, device_data must have been reinitialised as a dict
        assert isinstance(result.device_data, dict)

    async def test_tuneable_light_adds_color_temp(self):
        """Lines 168-169: tuneablelight type adds color_temp to status."""
        device_id = "dev-2"
        hive_id = "light-2"
        products = {hive_id: _TUNEABLE_PRODUCT}
        devices = {device_id: {"props": {"online": True}, "parent": None}}
        session = _make_session(products=products, devices=devices)

        light = Light(session=session)
        device = _make_device(
            hive_id=hive_id,
            device_id=device_id,
            hive_type="tuneablelight",
        )
        result = await light.get_light(device)

        assert "color_temp" in result.status

    async def test_colour_tuneable_light_in_colour_mode_adds_hs_color(self):
        """Lines 170-174: colourtuneablelight in COLOUR mode adds hs_color."""
        device_id = "dev-3"
        hive_id = "light-3"
        products = {hive_id: _COLOUR_TUNEABLE_PRODUCT}
        devices = {device_id: {"props": {"online": True}, "parent": None}}
        session = _make_session(products=products, devices=devices)

        light = Light(session=session)
        device = _make_device(
            hive_id=hive_id,
            device_id=device_id,
            hive_type="colourtuneablelight",
        )
        result = await light.get_light(device)

        assert "color_temp" in result.status
        assert result.status.get("mode") == "COLOUR"
        assert "hs_color" in result.status

    async def test_colour_tuneable_light_in_white_mode_no_hs_color(self):
        """Lines 170-172: colourtuneablelight in WHITE mode does NOT add hs_color."""
        device_id = "dev-4"
        hive_id = "light-4"
        products = {hive_id: _COLOUR_TUNEABLE_WHITE_PRODUCT}
        devices = {device_id: {"props": {"online": True}, "parent": None}}
        session = _make_session(products=products, devices=devices)

        light = Light(session=session)
        device = _make_device(
            hive_id=hive_id,
            device_id=device_id,
            hive_type="colourtuneablelight",
        )
        result = await light.get_light(device)

        assert result.status.get("mode") == "WHITE"
        assert "hs_color" not in result.status

    async def test_offline_device_calls_error_check(self):
        """Offline path: error_check is called and a default status is returned."""
        session = _make_session()
        session.attr.online_offline = AsyncMock(return_value=False)

        light = Light(session=session)
        device = _make_device()
        device.status = None

        result = await light.get_light(device)

        session.helper.error_check.assert_awaited_once()
        assert result.status == {"state": None}


class TestTurnOn:
    """Tests for Light.turn_on covering the color branch (line 212)."""

    async def test_turn_on_with_color_calls_set_color(self):
        """Line 212: passing color=[h,s,v] delegates to set_color."""
        hive_id = "light-1"
        products = {hive_id: {"type": "colourtuneablelight"}}
        session = _make_session(products=products)

        light = Light(session=session)
        device = _make_device(hive_id=hive_id, hive_type="colourtuneablelight")

        color = [120, 100, 100]
        await light.turn_on(device, brightness=None, color_temp=None, color=color)

        # set_color ultimately calls _execute_state_change → set_state
        session.api.set_state.assert_awaited_once()
        call_kwargs = session.api.set_state.call_args.kwargs
        assert call_kwargs.get("colourMode") == "COLOUR"
        assert call_kwargs.get("hue") == str(color[0])


# ---------------------------------------------------------------------------
# get_brightness — must return int, not float
# ---------------------------------------------------------------------------


class TestGetBrightnessReturnsInt:
    """get_brightness must return int, not float."""

    async def test_get_brightness_returns_int(self):
        """Brightness value is returned as int (not float) for HA compatibility."""
        from apyhiveapi.devices.light import HiveLight

        class StubLight(HiveLight):
            """Concrete stub for testing."""

        h = StubLight()
        h.session = MagicMock()
        h.session.data.products = {"h1": {"state": {"brightness": 50}}}
        d = Device(
            hive_id="h1",
            hive_name="L",
            hive_type="warmwhitelight",
            ha_type="light",
            device_id="d1",
            device_name="L",
            device_data={"online": True},
            ha_name="Light",
        )
        result = await h.get_brightness(d)
        assert isinstance(result, int), (
            f"Expected int, got {type(result).__name__}: {result!r}"
        )
        assert result == 127


class TestGetBrightnessNullValue:
    """A null brightness in the API payload must not raise TypeError."""

    async def test_null_brightness_returns_none(self):
        session = _make_session(
            products={
                "light-1": {
                    "state": {"status": "ON", "brightness": None},
                    "props": {},
                }
            },
        )
        light = Light(session=session)
        result = await light.get_brightness(_make_device())
        assert result is None


# ===========================================================================
# Migrated from test_remaining_branches.py
# ===========================================================================


class TestLightGetLightCacheMiss:
    """Lines 141->147: cache enabled but cached is None → normal execution."""

    async def test_cached_none_falls_through(self):
        session = _make_session(
            products={
                "light-1": {"state": {"status": "ON", "brightness": 100}, "props": {}}
            },
            devices={"dev-1": {"state": {}, "props": {}}},
        )
        light = Light(session=session)
        d = _make_device()
        session.should_use_cached_data.return_value = True
        session.get_cached_device.return_value = None
        result = await light.get_light(d)
        assert result is not None
        session.attr.online_offline.assert_called_once()
