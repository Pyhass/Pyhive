"""Tests for BoostMixin — shared by HiveHeating and HiveHotwater."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods
from unittest.mock import MagicMock

import pytest
from apyhiveapi.devices.boost import BoostMixin
from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.helper.map import Map

_BOOST_ON_MINUTES = 30
_BOOST_TIME_MINUTES = 45


def _make_handler(products):
    """Create a concrete BoostMixin instance with mocked session."""

    class ConcreteBoost(BoostMixin):
        """Concrete subclass used only for testing."""

    h = ConcreteBoost()
    session = MagicMock()
    session.data = Map(
        {
            "products": products,
            "devices": {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    h.session = session
    return h


def _make_device(hive_id="prod-1"):
    """Create a Device instance for testing."""
    return Device(
        hive_id=hive_id,
        hive_name="Test",
        hive_type="heating",
        ha_type="climate",
        device_id="dev-1",
        device_name="Test",
        device_data={"online": True},
    )


class TestGetBoostStatus:
    """Tests for BoostMixin.get_boost_status()."""

    @pytest.mark.asyncio
    async def test_int_minutes_returns_on(self):
        """Boost with minutes remaining returns ON."""
        h = _make_handler({"prod-1": {"state": {"boost": _BOOST_ON_MINUTES}}})
        assert await h.get_boost_status(_make_device()) == "ON"

    @pytest.mark.asyncio
    async def test_false_returns_off(self):
        """Boost value False returns OFF."""
        h = _make_handler({"prod-1": {"state": {"boost": False}}})
        assert await h.get_boost_status(_make_device()) == "OFF"

    @pytest.mark.asyncio
    async def test_none_returns_off(self):
        """Boost value None returns OFF."""
        h = _make_handler({"prod-1": {"state": {"boost": None}}})
        assert await h.get_boost_status(_make_device()) == "OFF"

    @pytest.mark.asyncio
    async def test_missing_boost_returns_off(self):
        """Missing boost key defaults to False, returns OFF."""
        h = _make_handler({"prod-1": {"state": {}}})
        assert await h.get_boost_status(_make_device()) == "OFF"

    @pytest.mark.asyncio
    async def test_missing_product_returns_none(self):
        """Missing product ID returns None on KeyError."""
        h = _make_handler({})
        assert await h.get_boost_status(_make_device()) is None

    @pytest.mark.asyncio
    async def test_zero_minutes_returns_off(self):
        """Boost with 0 minutes returns OFF (0 == False in dict lookup)."""
        h = _make_handler({"prod-1": {"state": {"boost": 0}}})
        assert await h.get_boost_status(_make_device()) == "OFF"

    @pytest.mark.asyncio
    async def test_missing_state_returns_none(self):
        """Missing state dict returns None on KeyError."""
        h = _make_handler({"prod-1": {}})
        assert await h.get_boost_status(_make_device()) is None


class TestGetBoostTime:
    """Tests for BoostMixin.get_boost_time()."""

    @pytest.mark.asyncio
    async def test_boost_on_returns_minutes(self):
        """Active boost returns remaining minutes."""
        h = _make_handler({"prod-1": {"state": {"boost": _BOOST_TIME_MINUTES}}})
        assert await h.get_boost_time(_make_device()) == _BOOST_TIME_MINUTES

    @pytest.mark.asyncio
    async def test_boost_off_returns_none(self):
        """Boost OFF returns None."""
        h = _make_handler({"prod-1": {"state": {"boost": False}}})
        assert await h.get_boost_time(_make_device()) is None

    @pytest.mark.asyncio
    async def test_boost_none_returns_none(self):
        """Boost None returns None."""
        h = _make_handler({"prod-1": {"state": {"boost": None}}})
        assert await h.get_boost_time(_make_device()) is None

    @pytest.mark.asyncio
    async def test_missing_boost_returns_none(self):
        """Missing boost key (defaults to OFF) returns None."""
        h = _make_handler({"prod-1": {"state": {}}})
        assert await h.get_boost_time(_make_device()) is None

    @pytest.mark.asyncio
    async def test_missing_product_returns_none(self):
        """Missing product ID returns None."""
        h = _make_handler({})
        assert await h.get_boost_time(_make_device()) is None

    @pytest.mark.asyncio
    async def test_zero_minutes_returns_none(self):
        """Boost with 0 minutes returns None (0 == False, so status is OFF)."""
        h = _make_handler({"prod-1": {"state": {"boost": 0}}})
        assert await h.get_boost_time(_make_device()) is None

    @pytest.mark.asyncio
    async def test_missing_state_returns_none(self):
        """Missing state dict returns None."""
        h = _make_handler({"prod-1": {}})
        assert await h.get_boost_time(_make_device()) is None
