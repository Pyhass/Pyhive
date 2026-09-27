"""Tests for DiscoveryMixin.start_session and create_devices."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveUnknownConfiguration,
)
from apyhiveapi.helper.hivedataclasses import SessionConfig
from apyhiveapi.helper.map import Map
from apyhiveapi.session.discovery import DiscoveryMixin

_POPULATED_PRODUCTS = {
    "prod-1": {"id": "prod-1", "type": "heating", "state": {"name": "Hall"}}
}
_POPULATED_DEVICES = {"dev-1": {"id": "dev-1", "type": "hub", "state": {"name": "Hub"}}}


def _make_stub(*, has_data=True):
    """DiscoveryMixin stub wired for start_session tests (create_devices mocked)."""

    class StubDiscovery(DiscoveryMixin):
        """Concrete subclass used only for testing."""

    s = StubDiscovery()
    s.config = SessionConfig()
    s.data = Map(
        {
            "products": _POPULATED_PRODUCTS if has_data else {},
            "devices": _POPULATED_DEVICES if has_data else {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    s.helper = MagicMock()
    s.helper.sanitize_payload = MagicMock(return_value={})
    s.auth = MagicMock()
    s.hub_id = None
    s.device_list = {
        "parent": [],
        "binary_sensor": [],
        "climate": [],
        "light": [],
        "sensor": [],
        "switch": [],
        "water_heater": [],
    }
    s.get_devices = AsyncMock(return_value=True)
    s.update_tokens = AsyncMock()
    s.create_devices = AsyncMock(return_value=s.device_list)
    return s


def _make_create_devices_stub():
    """DiscoveryMixin stub for testing create_devices directly (not mocked)."""

    class StubDiscovery(DiscoveryMixin):
        """Concrete subclass used only for testing."""

    s = StubDiscovery()
    s.config = SessionConfig()
    s.data = Map(
        {
            "products": {},
            "devices": {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    s.helper = MagicMock()
    s.helper.get_device_data = MagicMock(
        return_value={
            "id": "dev-1",
            "state": {"name": "Test"},
            "props": {"online": True},
        }
    )
    s.hub_id = None
    s.device_list = {
        "parent": [],
        "binary_sensor": [],
        "climate": [],
        "light": [],
        "sensor": [],
        "switch": [],
        "water_heater": [],
    }
    return s


class TestStartSession:
    """Tests for DiscoveryMixin.start_session."""

    async def test_file_mode_username_enables_file_and_succeeds(self):
        """'use@file.com' username activates file mode; start_session calls get_devices."""
        s = _make_stub()
        s.config.file = False
        await s.start_session({"username": "use@file.com"})
        assert s.config.file is True
        s.get_devices.assert_called_once()

    async def test_no_tokens_in_non_file_config_raises_unknown_configuration(self):
        """Non-file mode config without tokens raises HiveUnknownConfiguration."""
        s = _make_stub()
        s.config.file = False
        _cfg = {
            "username": "real@user.com",
            "password": "pass",  # pragma: allowlist secret
        }
        with pytest.raises(HiveUnknownConfiguration):
            await s.start_session(_cfg)

    async def test_tokens_in_config_calls_update_tokens(self):
        """Passing tokens in config triggers update_tokens(tokens, False)."""
        s = _make_stub()
        s.config.file = False
        tokens = {"token": "t", "accessToken": "a", "refreshToken": "r"}
        await s.start_session({"tokens": tokens})
        s.update_tokens.assert_called_once_with(tokens, False)

    async def test_file_mode_calls_create_devices_and_returns_list(self):
        """start_session returns the device list produced by create_devices."""
        s = _make_stub()
        s.config.file = True
        result = await s.start_session({})
        s.create_devices.assert_called_once()
        assert result is s.device_list


class TestCreateDevices:
    """Tests for DiscoveryMixin.create_devices product filtering."""

    async def test_product_with_error_key_is_skipped(self):
        """Products with an 'error' key are silently skipped."""
        s = _make_create_devices_stub()
        s.data["products"] = {
            "bad": {"id": "bad", "type": "heating", "error": "device not found"}
        }
        result = await s.create_devices()
        assert result["climate"] == []

    async def test_non_heating_group_product_is_skipped(self):
        """isGroup=True products of non-heating type are skipped."""
        s = _make_create_devices_stub()
        s.data["products"] = {
            "g1": {
                "id": "g1",
                "type": "activeplug",
                "isGroup": True,
                "state": {"name": "Group"},
            }
        }
        result = await s.create_devices()
        assert result["switch"] == []

    async def test_heating_group_product_is_not_skipped(self):
        """isGroup=True products of heating type are processed normally."""
        s = _make_create_devices_stub()
        s.data["products"] = {
            "h1": {
                "id": "h1",
                "type": "heating",
                "isGroup": True,
                "state": {"name": "Zone"},
            }
        }
        result = await s.create_devices()
        assert len(result["climate"]) == 1
