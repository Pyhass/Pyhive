"""Unit tests for HiveAttributes."""

# pylint: disable=too-few-public-methods

from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi.helper.device_attributes import HiveAttributes
from apyhiveapi.helper.hivedataclasses import SessionConfig
from apyhiveapi.helper.map import Map

BATTERY_75 = 75
BATTERY_50 = 50
BATTERY_80 = 80
BATTERY_42 = 42
BATTERY_90 = 90


def _make_attrs(devices=None, products=None, battery=None, mode=None):
    """Build a HiveAttributes instance backed by a minimal mock session."""
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
    config = SessionConfig()
    config.battery = set(battery) if battery else set()
    config.mode = set(mode) if mode else set()
    session.config = config
    session.helper = MagicMock()
    session.helper.error_check = AsyncMock()
    return HiveAttributes(session)


# ---------------------------------------------------------------------------
# online_offline
# ---------------------------------------------------------------------------


class TestOnlineOffline:
    """Tests for HiveAttributes.online_offline."""

    @pytest.mark.asyncio
    async def test_online_returns_true(self):
        """Online device reports True."""
        attrs = _make_attrs(devices={"d1": {"props": {"online": True}}})
        assert await attrs.online_offline("d1") is True

    @pytest.mark.asyncio
    async def test_offline_returns_false(self):
        """Offline device reports False."""
        attrs = _make_attrs(devices={"d1": {"props": {"online": False}}})
        assert await attrs.online_offline("d1") is False

    @pytest.mark.asyncio
    async def test_missing_device_returns_none(self):
        """Unknown device id returns None without raising."""
        attrs = _make_attrs()
        assert await attrs.online_offline("nope") is None

    @pytest.mark.asyncio
    async def test_device_without_props_returns_none(self):
        """A device entry that has no 'props' key should not raise — returns None."""
        attrs = _make_attrs(devices={"d1": {}})
        assert await attrs.online_offline("d1") is None


# ---------------------------------------------------------------------------
# get_battery
# ---------------------------------------------------------------------------


class TestGetBattery:
    """Tests for HiveAttributes.get_battery."""

    @pytest.mark.asyncio
    async def test_returns_battery_level(self):
        """Battery level is returned as the raw integer from props."""
        attrs = _make_attrs(devices={"d1": {"props": {"battery": BATTERY_75}}})
        result = await attrs.get_battery("d1")
        assert result == BATTERY_75

    @pytest.mark.asyncio
    async def test_missing_device_returns_none(self):
        """Unknown device id returns None without raising."""
        attrs = _make_attrs()
        assert await attrs.get_battery("nope") is None

    @pytest.mark.asyncio
    async def test_returns_correct_battery_level(self):
        """Battery level is returned as the raw integer from props."""
        attrs = _make_attrs(devices={"d1": {"props": {"battery": BATTERY_50}}})
        result = await attrs.get_battery("d1")
        assert result == BATTERY_50

    @pytest.mark.asyncio
    async def test_battery_zero_returned(self):
        """A battery level of 0 should be returned as 0, not treated as falsy/None."""
        attrs = _make_attrs(devices={"d1": {"props": {"battery": 0}}})
        assert await attrs.get_battery("d1") == 0


# ---------------------------------------------------------------------------
# get_mode
# ---------------------------------------------------------------------------


class TestGetMode:
    """Tests for HiveAttributes.get_mode."""

    @pytest.mark.asyncio
    async def test_returns_raw_mode_when_not_in_hivetoha(self):
        """HIVETOHA["Attribute"] maps True/False; a string mode passes through unchanged."""
        attrs = _make_attrs(products={"p1": {"state": {"mode": "SCHEDULE"}}})
        result = await attrs.get_mode("p1")
        assert result == "SCHEDULE"

    @pytest.mark.asyncio
    async def test_missing_product_returns_none(self):
        """Unknown product id returns None without raising."""
        attrs = _make_attrs()
        assert await attrs.get_mode("nope") is None

    @pytest.mark.asyncio
    async def test_manual_mode_passes_through(self):
        """MANUAL mode string is not in HIVETOHA["Attribute"] so it passes through."""
        attrs = _make_attrs(products={"p1": {"state": {"mode": "MANUAL"}}})
        result = await attrs.get_mode("p1")
        assert result == "MANUAL"

    @pytest.mark.asyncio
    async def test_true_value_returned_directly(self):
        """get_mode returns the raw mode value (True) without HIVETOHA translation."""
        attrs = _make_attrs(products={"p1": {"state": {"mode": True}}})
        result = await attrs.get_mode("p1")
        assert result is True

    @pytest.mark.asyncio
    async def test_false_value_returned_directly(self):
        """get_mode returns the raw mode value (False) without HIVETOHA translation."""
        attrs = _make_attrs(products={"p1": {"state": {"mode": False}}})
        result = await attrs.get_mode("p1")
        assert result is False


# ---------------------------------------------------------------------------
# state_attributes
# ---------------------------------------------------------------------------


class TestStateAttributes:
    """Tests for HiveAttributes.state_attributes."""

    @pytest.mark.asyncio
    async def test_device_in_products_includes_available(self):
        """Device found only in products still gets 'available' via online_offline."""
        attrs = _make_attrs(
            products={"p1": {"state": {"mode": "SCHEDULE"}}},
            devices={"p1": {"props": {"online": True}}},
        )
        result = await attrs.state_attributes("p1", "heating")
        assert "available" in result
        assert result["available"] is True

    @pytest.mark.asyncio
    async def test_device_only_in_products_no_devices_available_is_none(self):
        """Device present in products but absent from devices yields available == None."""
        attrs = _make_attrs(products={"p1": {"state": {"mode": "SCHEDULE"}}})
        result = await attrs.state_attributes("p1", "heating")
        assert "available" in result
        assert result["available"] is None

    @pytest.mark.asyncio
    async def test_device_in_battery_list_includes_battery(self):
        """Battery attribute present and formatted when device id is in config.battery."""
        attrs = _make_attrs(
            devices={"d1": {"props": {"online": True, "battery": BATTERY_80}}},
            battery=["d1"],
        )
        result = await attrs.state_attributes("d1", "trv")
        assert "battery" in result
        assert result["battery"] == "80%"

    @pytest.mark.asyncio
    async def test_battery_format_is_percent_string(self):
        """Battery value should be formatted as '<level>%'."""
        attrs = _make_attrs(
            devices={"d1": {"props": {"online": True, "battery": BATTERY_42}}},
            battery=["d1"],
        )
        result = await attrs.state_attributes("d1", "trv")
        assert result["battery"] == "42%"

    @pytest.mark.asyncio
    async def test_device_not_in_battery_list_omits_battery(self):
        """Battery attribute absent when device id is not in config.battery."""
        attrs = _make_attrs(
            devices={"d1": {"props": {"online": True, "battery": BATTERY_80}}},
        )
        result = await attrs.state_attributes("d1", "trv")
        assert "battery" not in result

    @pytest.mark.asyncio
    async def test_device_in_battery_list_but_battery_none_omits_battery(self):
        """Battery attribute absent when device is listed but get_battery returns None."""
        attrs = _make_attrs(
            devices={"d1": {"props": {"online": True}}},
            battery=["d1"],
        )
        result = await attrs.state_attributes("d1", "trv")
        assert "battery" not in result

    @pytest.mark.asyncio
    async def test_device_in_mode_list_includes_mode(self):
        """Mode attribute present when device id is in config.mode."""
        attrs = _make_attrs(
            products={"p1": {"state": {"mode": "MANUAL"}}},
            devices={"p1": {"props": {"online": True}}},
            mode=["p1"],
        )
        result = await attrs.state_attributes("p1", "heating")
        assert "mode" in result
        assert result["mode"] == "MANUAL"

    @pytest.mark.asyncio
    async def test_device_not_in_mode_list_omits_mode(self):
        """Mode attribute absent when device id is not in config.mode."""
        attrs = _make_attrs(
            products={"p1": {"state": {"mode": "MANUAL"}}},
            devices={"p1": {"props": {"online": True}}},
        )
        result = await attrs.state_attributes("p1", "heating")
        assert "mode" not in result

    @pytest.mark.asyncio
    async def test_device_absent_returns_empty_dict(self):
        """Device absent from both products and devices returns an empty dict."""
        attrs = _make_attrs()
        result = await attrs.state_attributes("missing", "heating")
        assert result == {}

    @pytest.mark.asyncio
    async def test_all_attributes_combined(self):
        """When device is in battery and mode lists all three attributes appear."""
        attrs = _make_attrs(
            products={"d1": {"state": {"mode": "SCHEDULE"}}},
            devices={"d1": {"props": {"online": True, "battery": BATTERY_90}}},
            battery=["d1"],
            mode=["d1"],
        )
        result = await attrs.state_attributes("d1", "heating")
        assert result["available"] is True
        assert result["battery"] == "90%"
        assert result["mode"] == "SCHEDULE"


class TestGetModeNoOp:
    """HiveAttributes.get_mode must return mode string directly (no HIVETOHA lookup)."""

    async def test_get_mode_returns_mode_string_unchanged(self):
        """get_mode returns the raw mode string, not a boolean-keyed HIVETOHA lookup."""
        session = MagicMock()
        session.data.products = {"p1": {"state": {"mode": "SCHEDULE"}}}
        attr = HiveAttributes(session)

        result = await attr.get_mode("p1")
        assert result == "SCHEDULE"


class TestGetBatteryNoDeadCall:
    """HiveAttributes.get_battery must not call error_check with integer state."""

    async def test_get_battery_returns_value_without_error_check_side_effects(self):
        """get_battery returns the battery level; error_check is not called with int."""
        session = MagicMock()
        session.data.devices = {"d1": {"props": {"battery": 85}}}
        attr = HiveAttributes(session)
        session.helper.error_check = AsyncMock()

        result = await attr.get_battery("d1")
        assert result == 85
        session.helper.error_check.assert_not_called()
