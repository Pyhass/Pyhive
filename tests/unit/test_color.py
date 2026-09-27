"""Extended branch-coverage tests for LightColorHandler (devices/color.py)."""

# pylint: disable=protected-access

from unittest.mock import MagicMock

from apyhiveapi.devices.color import LightColorHandler
from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.helper.map import Map


def _make_session(products=None):
    session = MagicMock()
    session.data = Map(
        {
            "products": products or {},
            "devices": {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    return session


def _make_handler(session):
    """Return a concrete LightColorHandler bound to *session*."""

    class ConcreteColorHandler(LightColorHandler):
        """Minimal concrete subclass for testing."""

    h = ConcreteColorHandler()
    h.session = session
    return h


def _make_device(hive_id="light-1"):
    return Device(
        hive_id=hive_id,
        hive_name="Test Light",
        hive_type="tuneablelight",
        ha_type="light",
        device_id="dev-1",
        device_name="Test Light",
        device_data={"online": True},
        ha_name="Test Light",
    )


class TestGetMinColorTemp:
    """Tests for LightColorHandler.get_min_color_temp KeyError path (lines 36-38)."""

    async def test_keyerror_returns_none(self):
        """Lines 36-38: missing colourTemperature key causes KeyError → returns None."""
        hive_id = "light-1"
        # Product exists but has no 'colourTemperature' key under 'props'
        products = {hive_id: {"props": {}}}
        session = _make_session(products=products)
        handler = _make_handler(session)
        device = _make_device(hive_id=hive_id)

        result = await handler.get_min_color_temp(device)

        assert result is None

    async def test_keyerror_on_missing_product_returns_none(self):
        """Lines 36-38: hive_id not in products → KeyError → returns None."""
        session = _make_session(products={})
        handler = _make_handler(session)
        device = _make_device(hive_id="unknown-id")

        result = await handler.get_min_color_temp(device)

        assert result is None


class TestGetMaxColorTemp:
    """Tests for LightColorHandler.get_max_color_temp KeyError path (lines 53-55)."""

    async def test_keyerror_returns_none(self):
        """Lines 53-55: missing colourTemperature.min key → KeyError → returns None."""
        hive_id = "light-1"
        # Product has colourTemperature but no 'min' key
        products = {hive_id: {"props": {"colourTemperature": {"max": 6500}}}}
        session = _make_session(products=products)
        handler = _make_handler(session)
        device = _make_device(hive_id=hive_id)

        result = await handler.get_max_color_temp(device)

        assert result is None

    async def test_keyerror_on_missing_product_returns_none(self):
        """Lines 53-55: hive_id not in products → KeyError → returns None."""
        session = _make_session(products={})
        handler = _make_handler(session)
        device = _make_device(hive_id="unknown-id")

        result = await handler.get_max_color_temp(device)

        assert result is None


class TestZeroDivisionGuards:
    """Colour-temperature methods must return None instead of raising ZeroDivisionError."""

    async def test_get_min_color_temp_zero_returns_none(self):
        """min colourTemperature == 0 must return None, not raise ZeroDivisionError.

        get_min_color_temp reads colourTemperature['max'] and divides by it,
        so 'max' must be 0 to trigger ZeroDivisionError.
        """
        session = _make_session(
            products={
                "light-1": {"props": {"colourTemperature": {"max": 0, "min": 153}}}
            }
        )
        h = _make_handler(session)
        device = _make_device()
        result = await h.get_min_color_temp(device)
        assert result is None

    async def test_get_max_color_temp_zero_returns_none(self):
        """max colourTemperature == 0 must return None, not raise ZeroDivisionError.

        get_max_color_temp reads colourTemperature['min'] and divides by it,
        so 'min' must be 0 to trigger ZeroDivisionError.
        """
        session = _make_session(
            products={
                "light-1": {"props": {"colourTemperature": {"max": 500, "min": 0}}}
            }
        )
        h = _make_handler(session)
        device = _make_device()
        result = await h.get_max_color_temp(device)
        assert result is None

    async def test_get_color_temp_zero_returns_none(self):
        """state colourTemperature == 0 must return None, not raise ZeroDivisionError."""
        session = _make_session(
            products={"light-1": {"state": {"colourTemperature": 0}}}
        )
        h = _make_handler(session)
        device = _make_device()
        result = await h.get_color_temp(device)
        assert result is None


# ---------------------------------------------------------------------------
# get_color — must return HS 2-tuple for HA hs_color, not RGB 3-tuple
# ---------------------------------------------------------------------------


class TestGetColorReturnsHSTuple:
    """get_color must return (hue_degrees, saturation_percent) 2-tuple for HA hs_color."""

    async def test_get_color_returns_two_tuple(self):
        """get_color returns a 2-tuple (not 3-tuple)."""
        session = _make_session(
            {"light-1": {"state": {"hue": 120, "saturation": 75, "value": 100}}}
        )
        h = _make_handler(session)
        device = _make_device()
        result = await h.get_color(device)
        assert result is not None
        assert len(result) == 2, f"Expected 2-tuple (hue, sat), got {result!r}"

    async def test_get_color_returns_correct_hue_and_saturation(self):
        """get_color returns (hue, saturation) values matching API data."""
        session = _make_session(
            {"light-1": {"state": {"hue": 180, "saturation": 50, "value": 80}}}
        )
        h = _make_handler(session)
        device = _make_device()
        result = await h.get_color(device)
        assert result == (180, 50)
