"""Unit tests for BaseDeviceHandler shared plumbing."""

# pylint: disable=protected-access,too-few-public-methods,attribute-defined-outside-init

from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi.helper.device_handler_base import BaseDeviceHandler
from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.helper.map import Map


def _make_session(products=None):
    """Build a minimal mock session with configurable products data."""
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
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.api = MagicMock()
    session.api.set_state = AsyncMock(return_value={"original": 200, "parsed": {}})
    return session


def _make_handler(session):
    """Instantiate a concrete BaseDeviceHandler subclass bound to *session*."""

    class ConcreteHandler(BaseDeviceHandler):
        """Minimal concrete subclass used only for testing."""

    h = ConcreteHandler()
    h.session = session
    return h


def _make_device(hive_id="prod-1", device_id="dev-1", online=True):
    """Return a Device with sensible defaults."""
    return Device(
        hive_id=hive_id,
        hive_name="Test",
        hive_type="heating",
        ha_type="climate",
        device_id=device_id,
        device_name="Test",
        device_data={"online": online},
    )


class TestGetProductState:
    """Tests for BaseDeviceHandler._get_product_state."""

    def test_happy_path(self):
        """Returns the deeply-nested value when all keys exist."""
        session = _make_session({"prod-1": {"state": {"mode": "SCHEDULE"}}})
        h = _make_handler(session)
        d = _make_device()
        assert h._get_product_state(d, "state", "mode") == "SCHEDULE"

    def test_first_key_missing_returns_default(self):
        """Returns None when the first path key is absent."""
        session = _make_session({"prod-1": {}})
        h = _make_handler(session)
        d = _make_device()
        assert h._get_product_state(d, "missing_key") is None

    def test_nested_key_missing_returns_default(self):
        """Returns None when a nested path key is absent."""
        session = _make_session({"prod-1": {"state": {}}})
        h = _make_handler(session)
        d = _make_device()
        assert h._get_product_state(d, "state", "mode") is None

    def test_explicit_default_param(self):
        """Returns the caller-supplied default when a key is missing."""
        session = _make_session({"prod-1": {}})
        h = _make_handler(session)
        d = _make_device()
        assert h._get_product_state(d, "missing", default="fallback") == "fallback"

    def test_product_not_in_data_returns_default(self):
        """Returns None when the product ID is not in session data."""
        session = _make_session({})
        h = _make_handler(session)
        d = _make_device()
        assert h._get_product_state(d, "state") is None


class TestMapHiveToHa:
    """Tests for BaseDeviceHandler._map_hive_to_ha."""

    def test_known_key_maps_correctly(self):
        """Maps ON/OFF through the Switch mapping to True/False."""
        session = _make_session()
        h = _make_handler(session)
        assert h._map_hive_to_ha("Switch", "ON") is True
        assert h._map_hive_to_ha("Switch", "OFF") is False

    def test_unknown_value_returns_value_unchanged(self):
        """Returns the raw value when it is not in the mapping."""
        session = _make_session()
        h = _make_handler(session)
        assert h._map_hive_to_ha("Switch", "UNKNOWN") == "UNKNOWN"

    def test_fallback_param_used_when_not_in_mapping(self):
        """Returns fallback when provided and value is not mapped."""
        session = _make_session()
        h = _make_handler(session)
        assert h._map_hive_to_ha("Switch", "UNKNOWN", fallback="default") == "default"

    def test_unknown_mapping_key_returns_value(self):
        """Returns the raw value when the mapping key itself does not exist."""
        session = _make_session()
        h = _make_handler(session)
        assert h._map_hive_to_ha("NonExistentType", "val") == "val"


class TestExecuteStateChange:
    """Tests for BaseDeviceHandler._execute_state_change."""

    async def test_product_not_in_data_returns_false(self):
        """Returns False immediately when product is absent from session data."""
        session = _make_session({})
        h = _make_handler(session)
        d = _make_device()
        assert await h._execute_state_change(d, mode="MANUAL") is False

    async def test_device_offline_returns_false(self):
        """Returns False when device_data reports the device as offline."""
        session = _make_session({"prod-1": {"type": "heating"}})
        h = _make_handler(session)
        d = _make_device(online=False)
        assert await h._execute_state_change(d, mode="MANUAL") is False

    async def test_device_data_not_dict_returns_false(self):
        """Returns False when device_data is not a dict."""
        session = _make_session({"prod-1": {"type": "heating"}})
        h = _make_handler(session)
        d = _make_device()
        d.device_data = None
        assert await h._execute_state_change(d, mode="MANUAL") is False

    async def test_http_200_returns_true_and_calls_get_devices(self):
        """Returns True on HTTP 200 and refreshes device data via get_devices."""
        session = _make_session({"prod-1": {"type": "heating"}})
        session.api.set_state = AsyncMock(return_value={"original": 200, "parsed": {}})
        h = _make_handler(session)
        d = _make_device()
        result = await h._execute_state_change(d, mode="MANUAL")
        assert result is True
        session.hive_refresh_tokens.assert_called_once()
        session.get_devices.assert_called_once_with("prod-1")

    async def test_non_200_returns_false(self):
        """Returns False on non-200 HTTP status and does not call get_devices."""
        session = _make_session({"prod-1": {"type": "heating"}})
        session.api.set_state = AsyncMock(return_value={"original": 500, "parsed": {}})
        h = _make_handler(session)
        d = _make_device()
        result = await h._execute_state_change(d, mode="MANUAL")
        assert result is False
        session.get_devices.assert_not_called()

    async def test_malformed_set_state_response_raises_key_error(self):
        """KeyError propagates when set_state response is missing 'original' key."""
        session = _make_session({"prod-1": {"type": "heating"}})
        session.api.set_state = AsyncMock(return_value={"parsed": {}})
        h = _make_handler(session)
        d = _make_device()
        with pytest.raises(KeyError):
            await h._execute_state_change(d, mode="MANUAL")
