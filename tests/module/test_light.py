"""Tests for Light / HiveLight and LightColorHandler."""

# pylint: disable=too-few-public-methods
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.light import Light
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_HTTP_OK = 200
_BRIGHTNESS_PCT = 50
_BRIGHTNESS_HA = int((_BRIGHTNESS_PCT / 100) * 255)
_BRIGHTNESS_RAW = 80
_BRIGHTNESS_CONVERTED = int((_BRIGHTNESS_RAW / 100) * 255)
_BRIGHTNESS_SET = 128
_COLOR_TEMP_KELVIN = 4000
_COLOR_TEMP_MIRED = round((1 / _COLOR_TEMP_KELVIN) * 1_000_000)
_CT_MAX_KELVIN = 6500
_CT_MIN_KELVIN = 2700
_CT_MIN_MIRED = round((1 / _CT_MAX_KELVIN) * 1_000_000)
_CT_MAX_MIRED = round((1 / _CT_MIN_KELVIN) * 1_000_000)
_HSV_HUE = 120
_HSV_SAT = 100
_HSV_VAL = 100
_COLOR_TUPLE = (_HSV_HUE, _HSV_SAT)


def _make_light(products=None, devices=None):
    """Create a Light instance with a fully mocked session."""
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
    session.api.set_state = AsyncMock(return_value={"original": _HTTP_OK, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return Light(session=session)


def _make_device(hive_id="light-1", device_id="dev-1", hive_type="warmwhitelight"):
    """Return a minimal light Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Lamp",
        hive_type=hive_type,
        ha_type="light",
        device_id=device_id,
        device_name="Lamp",
        device_data={"online": True},
        ha_name="Lamp",
    )


class TestGetState:
    """Tests for HiveLight.get_state."""

    async def test_on_returns_true(self):
        """Status ON maps to True via HIVETOHA Light mapping."""
        light = _make_light({"light-1": {"state": {"status": "ON"}}})
        assert await light.get_state(_make_device()) is True

    async def test_off_returns_false(self):
        """Status OFF maps to False via HIVETOHA Light mapping."""
        light = _make_light({"light-1": {"state": {"status": "OFF"}}})
        assert await light.get_state(_make_device()) is False

    async def test_missing_returns_none(self):
        """Missing product key returns None on KeyError."""
        light = _make_light()
        assert await light.get_state(_make_device()) is None


class TestGetBrightness:
    """Tests for HiveLight.get_brightness."""

    async def test_converts_percentage_to_255_scale(self):
        """Brightness percentage is converted to 0–255 scale."""
        light = _make_light({"light-1": {"state": {"brightness": _BRIGHTNESS_PCT}}})
        result = await light.get_brightness(_make_device())
        assert result == _BRIGHTNESS_HA

    async def test_missing_returns_none(self):
        """Missing product or brightness key returns None."""
        light = _make_light()
        assert await light.get_brightness(_make_device()) is None


class TestSetStatus:
    """Tests for HiveLight.set_status_on and set_status_off."""

    async def test_set_on_calls_execute_with_status_on(self):
        """set_status_on calls _execute_state_change with status='ON' and returns True."""
        light = _make_light({"light-1": {"type": "warmwhitelight"}})
        result = await light.set_status_on(_make_device())
        assert result is True
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("status") == "ON"

    async def test_set_off_calls_execute_with_status_off(self):
        """set_status_off calls _execute_state_change with status='OFF' and returns True."""
        light = _make_light({"light-1": {"type": "warmwhitelight"}})
        result = await light.set_status_off(_make_device())
        assert result is True
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("status") == "OFF"


class TestSetBrightness:
    """Tests for HiveLight.set_brightness."""

    async def test_calls_execute_with_status_on_and_brightness(self):
        """set_brightness sends status ON and the brightness value to the API."""
        light = _make_light({"light-1": {"type": "warmwhitelight"}})
        await light.set_brightness(_make_device(), _BRIGHTNESS_SET)
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("status") == "ON"
        assert kwargs.get("brightness") == _BRIGHTNESS_SET


class TestTurnOn:
    """Tests for Light.turn_on."""

    async def test_brightness_routes_to_set_brightness(self):
        """turn_on with brightness routes to set_brightness."""
        light = _make_light({"light-1": {"type": "warmwhitelight"}})
        await light.turn_on(
            _make_device(), brightness=_BRIGHTNESS_SET, color_temp=None, color=None
        )
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("brightness") == _BRIGHTNESS_SET

    async def test_color_temp_routes_to_set_color_temp(self):
        """turn_on with color_temp routes to set_color_temp."""
        light = _make_light(
            {"light-1": {"type": "tuneablelight", "state": {}, "props": {}}}
        )
        await light.turn_on(
            _make_device(hive_type="tuneablelight"),
            brightness=None,
            color_temp=_COLOR_TEMP_KELVIN,
            color=None,
        )
        _, kwargs = light.session.api.set_state.call_args
        assert "colourTemperature" in kwargs

    async def test_all_none_calls_set_status_on(self):
        """turn_on with all None arguments falls back to set_status_on."""
        light = _make_light({"light-1": {"type": "warmwhitelight"}})
        result = await light.turn_on(
            _make_device(), brightness=None, color_temp=None, color=None
        )
        assert result is True
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("status") == "ON"


class TestTurnOff:
    """Tests for Light.turn_off."""

    async def test_calls_set_status_off(self):
        """turn_off delegates to set_status_off and returns True on success."""
        light = _make_light({"light-1": {"type": "warmwhitelight"}})
        result = await light.turn_off(_make_device())
        assert result is True


class TestGetLight:
    """Tests for Light.get_light."""

    async def test_online_populates_state_and_brightness(self):
        """Online warm-white light gets state and brightness populated."""
        light = _make_light(
            {
                "light-1": {
                    "type": "warmwhitelight",
                    "state": {"status": "ON", "brightness": _BRIGHTNESS_RAW},
                },
            }
        )
        light.session.data.devices["dev-1"] = {"props": {"online": True}}
        d = _make_device()
        result = await light.get_light(d)
        assert result.status["state"] is True
        assert result.status["brightness"] == _BRIGHTNESS_CONVERTED

    async def test_offline_defaults_status(self):
        """Offline device sets status to {'state': None}."""
        light = _make_light()
        light.session.attr.online_offline.return_value = False
        d = _make_device()
        result = await light.get_light(d)
        assert result.status == {"state": None}

    async def test_cached_returns_cached(self):
        """get_light returns the cached device when should_use_cached_data is True."""
        light = _make_light()
        light.session.should_use_cached_data.return_value = True
        cached = _make_device()
        light.session.get_cached_device.return_value = cached
        result = await light.get_light(_make_device())
        assert result is cached


class TestLightColorHandler:
    """Tests for LightColorHandler methods (mixed into HiveLight)."""

    async def test_get_min_color_temp_converts_kelvin(self):
        """get_min_color_temp returns mireds derived from colourTemperature.max kelvin."""
        light = _make_light(
            {
                "light-1": {
                    "props": {
                        "colourTemperature": {
                            "max": _CT_MAX_KELVIN,
                            "min": _CT_MIN_KELVIN,
                        }
                    },
                    "state": {},
                }
            }
        )
        result = await light.get_min_color_temp(_make_device())
        assert result == _CT_MIN_MIRED

    async def test_get_max_color_temp_converts_kelvin(self):
        """get_max_color_temp returns mireds derived from colourTemperature.min kelvin."""
        light = _make_light(
            {
                "light-1": {
                    "props": {
                        "colourTemperature": {
                            "max": _CT_MAX_KELVIN,
                            "min": _CT_MIN_KELVIN,
                        }
                    },
                    "state": {},
                }
            }
        )
        result = await light.get_max_color_temp(_make_device())
        assert result == _CT_MAX_MIRED

    async def test_get_color_temp_returns_mireds(self):
        """get_color_temp converts the current kelvin value to mireds."""
        light = _make_light(
            {
                "light-1": {
                    "state": {"colourTemperature": _COLOR_TEMP_KELVIN},
                    "props": {},
                }
            }
        )
        result = await light.get_color_temp(_make_device())
        assert result == _COLOR_TEMP_MIRED

    async def test_get_color_temp_missing_returns_none(self):
        """get_color_temp returns None when the product or key is absent."""
        light = _make_light()
        assert await light.get_color_temp(_make_device()) is None

    async def test_get_color_returns_rgb_tuple(self):
        """get_color returns an (hue, saturation) 2-tuple for HA hs_color."""
        light = _make_light(
            {
                "light-1": {
                    "state": {
                        "hue": _HSV_HUE,
                        "saturation": _HSV_SAT,
                        "value": _HSV_VAL,
                    }
                }
            }
        )
        result = await light.get_color(_make_device())
        assert result == _COLOR_TUPLE

    async def test_get_color_missing_returns_none(self):
        """get_color returns None when the product or HSV keys are absent."""
        light = _make_light()
        assert await light.get_color(_make_device()) is None

    async def test_get_color_mode_returns_colour(self):
        """get_color_mode returns the colourMode string from product state."""
        light = _make_light({"light-1": {"state": {"colourMode": "COLOUR"}}})
        assert await light.get_color_mode(_make_device()) == "COLOUR"

    async def test_get_color_mode_missing_returns_none(self):
        """get_color_mode returns None when the product or key is absent."""
        light = _make_light()
        assert await light.get_color_mode(_make_device()) is None

    async def test_set_color_temp_tuneable_no_colour_mode(self):
        """set_color_temp for tuneablelight omits the colourMode kwarg."""
        light = _make_light(
            {"light-1": {"type": "tuneablelight", "state": {}, "props": {}}}
        )
        d = _make_device(hive_type="tuneablelight")
        await light.set_color_temp(d, _COLOR_TEMP_KELVIN)
        _, kwargs = light.session.api.set_state.call_args
        assert "colourTemperature" in kwargs
        assert "colourMode" not in kwargs

    async def test_set_color_temp_colour_tuneable_adds_white_mode(self):
        """set_color_temp for colourtuneablelight adds colourMode='WHITE'."""
        light = _make_light(
            {"light-1": {"type": "colourtuneablelight", "state": {}, "props": {}}}
        )
        d = _make_device(hive_type="colourtuneablelight")
        await light.set_color_temp(d, _COLOR_TEMP_KELVIN)
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("colourMode") == "WHITE"

    async def test_set_color_passes_hsv_as_strings(self):
        """set_color sends colourMode COLOUR and HSV values as strings to the API."""
        light = _make_light(
            {"light-1": {"type": "colourtuneablelight", "state": {}, "props": {}}}
        )
        d = _make_device(hive_type="colourtuneablelight")
        await light.set_color(d, [_HSV_HUE, _HSV_SAT, _HSV_VAL])
        _, kwargs = light.session.api.set_state.call_args
        assert kwargs.get("colourMode") == "COLOUR"
        assert kwargs.get("hue") == str(_HSV_HUE)
        assert kwargs.get("saturation") == str(_HSV_SAT)
        assert kwargs.get("value") == str(_HSV_VAL)
