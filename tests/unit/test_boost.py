"""Extended branch-coverage tests for BoostMixin (devices/boost.py)."""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.boost import BoostMixin
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
    """Return a concrete BoostMixin instance bound to *session*."""

    class ConcreteBoost(BoostMixin):
        """Minimal concrete subclass for testing."""

    h = ConcreteBoost()
    h.session = session
    return h


def _make_device(hive_id="heating-1"):
    return Device(
        hive_id=hive_id,
        hive_name="Heating Zone",
        hive_type="heating",
        ha_type="climate",
        device_id="dev-1",
        device_name="Heating Zone",
        device_data={"online": True},
        ha_name="Heating Zone",
    )


class TestGetBoostTime:
    """Tests for BoostMixin.get_boost_time covering the KeyError path (lines 45-46)."""

    async def test_boost_on_but_keyerror_returns_none(self):
        """Lines 45-46: get_boost_status returns ON but state has no 'boost' key → None."""
        hive_id = "heating-1"
        # state has no 'boost' key so data["state"]["boost"] will raise KeyError
        products = {hive_id: {"state": {}}}
        session = _make_session(products=products)
        handler = _make_handler(session)
        device = _make_device(hive_id=hive_id)

        # Patch get_boost_status on the instance to return "ON" directly,
        # bypassing the HIVETOHA lookup so we can reach the KeyError branch.
        handler.get_boost_status = AsyncMock(return_value="ON")

        result = await handler.get_boost_time(device)

        assert result is None

    async def test_boost_off_returns_none_without_entering_try(self):
        """Boost status is OFF → skips the try block entirely → returns None."""
        hive_id = "heating-2"
        products = {hive_id: {"state": {"boost": False}}}
        session = _make_session(products=products)
        handler = _make_handler(session)
        device = _make_device(hive_id=hive_id)

        result = await handler.get_boost_time(device)

        assert result is None

    async def test_boost_on_with_valid_data_returns_time(self):
        """Boost is ON and data is present → returns the boost time value."""
        hive_id = "heating-3"
        products = {hive_id: {"state": {"boost": 30}}}
        session = _make_session(products=products)
        handler = _make_handler(session)
        device = _make_device(hive_id=hive_id)

        # get_boost_status reads HIVETOHA["Boost"].get(30, "ON") → "ON" (not in mapping)
        result = await handler.get_boost_time(device)

        assert result == 30
