"""Extended branch-coverage tests for DiscoveryMixin.start_session and create_devices."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveConnectionError,
    HiveReauthRequired,
    HiveUnknownConfiguration,
)
from apyhiveapi.helper.hivedataclasses import EntityConfig, SessionConfig, SessionTokens
from apyhiveapi.helper.map import Map
from apyhiveapi.session.discovery import DiscoveryMixin

_POPULATED_PRODUCTS = {
    "prod-1": {"id": "prod-1", "type": "heating", "state": {"name": "Hall"}}
}
_POPULATED_DEVICES = {"dev-1": {"id": "dev-1", "type": "hub", "state": {"name": "Hub"}}}


def _make_stub(*, has_data=True):
    """Return a DiscoveryMixin stub wired for start_session tests (create_devices mocked)."""

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
    s.tokens = SessionTokens()
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


def _make_create_stub():
    """Return a DiscoveryMixin stub for testing create_devices directly (not mocked)."""

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
            "user": {"temperatureUnit": "C"},
        }
    )
    s.helper = MagicMock()
    s.helper.get_device_data = MagicMock(
        return_value={
            "id": "dev-1",
            "state": {"name": "Test Device"},
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


# ---------------------------------------------------------------------------
# start_session — config branches
# ---------------------------------------------------------------------------


class TestStartSessionExtended:
    """Tests for start_session config-processing branches."""

    async def test_with_tokens_config_calls_update_tokens(self):
        """Passing 'tokens' in non-file config calls update_tokens(tokens, False)."""
        s = _make_stub()
        s.config.file = False
        tokens = {"token": "t", "accessToken": "a", "refreshToken": "r"}
        await s.start_session({"tokens": tokens})
        s.update_tokens.assert_called_once_with(tokens, False)

    async def test_with_username_config_sets_auth_username(self):
        """Passing 'username' alongside 'tokens' in non-file config sets auth.username."""
        s = _make_stub()
        s.config.file = False
        tokens = {"token": "t", "accessToken": "a", "refreshToken": "r"}
        await s.start_session({"tokens": tokens, "username": "user@test.com"})
        assert s.auth.username == "user@test.com"

    async def test_with_password_config_sets_auth_password(self):
        """Passing 'password' alongside 'tokens' in non-file config sets auth.password."""
        s = _make_stub()
        s.config.file = False
        tokens = {"token": "t", "accessToken": "a", "refreshToken": "r"}
        await s.start_session(
            {"tokens": tokens, "password": "secret"}  # pragma: allowlist secret
        )
        assert s.auth.password == "secret"  # pragma: allowlist secret

    async def test_with_device_data_3_items_sets_auth_keys(self):
        """3-item device_data sets device_group_key, device_key, device_password on auth."""
        s = _make_stub()
        s.config.file = False
        await s.start_session(
            {
                "tokens": {},
                "device_data": ["grp-key", "dev-key", "dev-pass"],
            }
        )
        assert s.auth.device_group_key == "grp-key"
        assert s.auth.device_key == "dev-key"
        assert s.auth.device_password == "dev-pass"  # pragma: allowlist secret

    async def test_with_device_data_too_short_raises_unknown_configuration(self):
        """device_data with fewer than 3 items raises HiveUnknownConfiguration."""
        s = _make_stub()
        s.config.file = False
        with pytest.raises(HiveUnknownConfiguration):
            await s.start_session(
                {
                    "tokens": {},
                    "device_data": ["grp-key", "dev-key"],
                }
            )

    async def test_with_device_data_4_items_sets_token_created(self):
        """4-item device_data with a token_created timestamp sets tokens.token_created."""
        s = _make_stub()
        s.config.file = False
        created_ts = datetime(2024, 1, 15, 10, 30, 0)
        await s.start_session(
            {
                "tokens": {},
                "device_data": ["grp-key", "dev-key", "dev-pass", created_ts],
            }
        )
        assert s.tokens.token_created == created_ts

    async def test_with_device_data_4_items_none_token_created_not_set(self):
        """4-item device_data where token_created is None — does not overwrite token_created."""
        s = _make_stub()
        s.config.file = False
        original_created = s.tokens.token_created
        await s.start_session(
            {
                "tokens": {},
                "device_data": ["grp-key", "dev-key", "dev-pass", None],
            }
        )
        assert s.tokens.token_created == original_created

    async def test_no_tokens_and_not_file_raises_unknown_configuration(self):
        """Non-file config without 'tokens' raises HiveUnknownConfiguration."""
        s = _make_stub()
        s.config.file = False
        with pytest.raises(HiveUnknownConfiguration):
            await s.start_session({"username": "user@test.com"})

    async def test_empty_devices_after_get_devices_raises_unknown_configuration(self):
        """start_session raises HiveUnknownConfiguration when data.devices is empty post-poll."""
        s = _make_stub(has_data=False)
        s.config.file = True
        with pytest.raises(HiveUnknownConfiguration):
            await s.start_session({})

    async def test_none_config_defaults_to_empty_dict(self):
        """start_session(None) is treated as start_session({}) — set file mode separately."""
        s = _make_stub()
        s.config.file = True
        # Should not raise; equivalent to passing {}
        result = await s.start_session(None)
        assert result is s.device_list

    async def test_file_mode_username_skips_token_branch(self):
        """'use@file.com' activates file mode so 'tokens' branch is skipped."""
        s = _make_stub()
        s.config.file = False
        # Even if tokens is present, file mode skips the update_tokens call
        await s.start_session({"username": "use@file.com", "tokens": {}})
        s.update_tokens.assert_not_called()


# ---------------------------------------------------------------------------
# create_devices — device processing
# ---------------------------------------------------------------------------


class TestCreateDevicesExtended:
    """Tests for create_devices branches not covered by the main test files."""

    async def test_no_hub_device_hub_id_stays_none(self):
        """Devices list with no 'hub' type leaves hub_id as None (else branch of for-loop)."""
        s = _make_create_stub()
        s.data["devices"] = {
            "trv-1": {"id": "trv-1", "type": "trv", "state": {"name": "TRV"}}
        }
        s.data["products"] = {}
        await s.create_devices()
        assert s.hub_id is None

    async def test_hub_device_sets_hub_id(self):
        """Devices list with a 'hub' type sets hub_id to that device's ID."""
        s = _make_create_stub()
        s.data["devices"] = {
            "hub-42": {"id": "hub-42", "type": "hub", "state": {"name": "My Hub"}}
        }
        await s.create_devices()
        assert s.hub_id == "hub-42"

    async def test_product_with_error_key_is_skipped(self):
        """Products with an 'error' key are silently skipped."""
        s = _make_create_stub()
        s.data["products"] = {
            "bad": {"id": "bad", "type": "heating", "error": "device not found"}
        }
        result = await s.create_devices()
        assert result["climate"] == []

    async def test_non_heating_group_product_skipped(self):
        """isGroup=True products of non-heating type are not added to any list."""
        s = _make_create_stub()
        s.data["products"] = {
            "grp-1": {
                "id": "grp-1",
                "type": "activeplug",
                "isGroup": True,
                "state": {"name": "Plug Group"},
            }
        }
        result = await s.create_devices()
        assert result["switch"] == []

    async def test_heating_group_product_not_skipped(self):
        """isGroup=True products of heating type are processed and added."""
        s = _make_create_stub()
        s.data["products"] = {
            "h-grp": {
                "id": "h-grp",
                "type": "heating",
                "isGroup": True,
                "state": {"name": "Heating Zone"},
            }
        }
        result = await s.create_devices()
        assert len(result["climate"]) == 1

    async def test_multiple_devices_all_processed(self):
        """Multiple devices in the device list are all processed."""
        s = _make_create_stub()
        s.data["devices"] = {
            "hub-1": {"id": "hub-1", "type": "hub", "state": {"name": "Hub"}},
            "trv-1": {"id": "trv-1", "type": "trv", "state": {"name": "TRV"}},
        }
        s.data["products"] = {}
        await s.create_devices()
        # Hub is found; hub_id is set to the hub device
        assert s.hub_id == "hub-1"

    async def test_action_processed_as_switch(self):
        """Actions in data.actions are added to device_list['switch']."""
        s = _make_create_stub()
        s.data["actions"] = {
            "act-1": {"id": "act-1", "name": "Good Night", "type": "action"}
        }
        result = await s.create_devices()
        assert len(result["switch"]) == 1
        assert result["switch"][0].hive_type == "action"

    async def test_returns_device_list_dict(self):
        """create_devices always returns a dict with the expected HA entity keys."""
        s = _make_create_stub()
        result = await s.create_devices()
        for key in (
            "parent",
            "binary_sensor",
            "climate",
            "light",
            "sensor",
            "switch",
            "water_heater",
        ):
            assert key in result

    async def test_product_with_error_and_valid_both_present_only_valid_added(self):
        """Only products without 'error' are added when both types coexist."""
        s = _make_create_stub()
        s.data["products"] = {
            "bad": {"id": "bad", "type": "heating", "error": "broken"},
            "good": {"id": "good", "type": "heating", "state": {"name": "Hall"}},
        }
        result = await s.create_devices()
        assert len(result["climate"]) == 1
        assert result["climate"][0].hive_id == "good"


# ---------------------------------------------------------------------------
# start_session raises wrong exception for empty device data
# ---------------------------------------------------------------------------


class TestStartSessionWrongException:
    """start_session must raise HiveUnknownConfiguration (not HiveReauthRequired) for empty data."""

    async def test_empty_devices_raises_unknown_configuration(self):
        """start_session raises HiveUnknownConfiguration when API returns no devices."""
        s = _make_stub(has_data=False)
        s.get_devices = AsyncMock()

        with pytest.raises(HiveUnknownConfiguration):
            await s.start_session({})

    async def test_does_not_raise_reauth_for_empty_data(self):
        """start_session must NOT raise HiveReauthRequired when device data is empty."""
        s = _make_stub(has_data=False)
        s.get_devices = AsyncMock()

        with pytest.raises(Exception) as exc_info:
            await s.start_session({})

        assert not isinstance(exc_info.value, HiveReauthRequired), (
            "HiveReauthRequired must not be raised for empty device list"
        )


class TestStartSessionFetchFailed:
    """A failed device fetch is a transient error, not an unknown configuration."""

    async def test_failed_fetch_raises_connection_error(self):
        """start_session raises HiveConnectionError when get_devices fails."""
        s = _make_stub(has_data=False)
        s.get_devices = AsyncMock(return_value=False)

        with pytest.raises(HiveConnectionError):
            await s.start_session({})

    async def test_failed_fetch_with_cached_data_still_creates_devices(self):
        """Data already loaded is used even if this fetch failed."""
        s = _make_stub(has_data=True)
        s.get_devices = AsyncMock(return_value=False)

        result = await s.start_session({})

        assert result is s.device_list


# ---------------------------------------------------------------------------
# create_devices — bare d["id"] and p["id"] crash when id key is absent
# ---------------------------------------------------------------------------


class TestBareIdAccess:
    """create_devices must use .get('id', fallback) instead of bare ['id'] access."""

    async def test_battery_device_without_id_does_not_crash(self):
        """Device with no 'id' key in battery-type must not raise KeyError."""
        s = _make_create_stub()
        s.data["devices"] = {
            "trv-key": {
                "type": "trv",
                "state": {"name": "TRV"},
                "props": {},
            }
        }
        s.config.battery = set()
        try:
            await s.create_devices()
        except KeyError as err:
            pytest.fail(f"KeyError raised for missing 'id' in device: {err}")

    async def test_mode_product_without_id_does_not_crash(self):
        """Product with no 'id' key in mode-type must not raise KeyError."""
        s = _make_create_stub()
        s.data["products"] = {
            "heating-key": {
                "type": "heating",
                "state": {"name": "Hall"},
            }
        }
        s.config.mode = set()
        try:
            await s.create_devices()
        except KeyError as err:
            pytest.fail(f"KeyError raised for missing 'id' in product: {err}")


# ===========================================================================
# Migrated from test_remaining_branches.py
# ===========================================================================


class TestCreateDevicesEntityConfigKwargs:
    """Lines 224->226, 226->228, 228->230: entity_config kwarg population in DEVICES loop."""

    async def test_entity_config_with_all_fields_populates_kwargs(self):
        """EntityConfig with ha_name, hive_type, and category all set → all kwargs passed."""
        s = _make_create_stub()
        s.data["devices"] = {
            "dev-1": {
                "id": "dev-1",
                "type": "hub",
                "state": {"name": "My Hub"},
                "props": {},
            }
        }
        entity_cfg = EntityConfig(
            entity_type="binary_sensor",
            ha_name="Hub Status",
            hive_type="Connectivity",
            category="diagnostic",
        )
        with patch("apyhiveapi.session.discovery.DEVICES", {"hub": [entity_cfg]}):
            result = await s.create_devices()
        assert len(result["binary_sensor"]) == 1
        created = result["binary_sensor"][0]
        assert created.hive_type == "Connectivity"
        assert created.category == "diagnostic"

    async def test_entity_config_empty_fields_does_not_add_to_kwargs(self):
        """EntityConfig with empty ha_name and hive_type does not inject those keys."""
        s = _make_create_stub()
        s.data["devices"] = {
            "dev-1": {
                "id": "dev-1",
                "type": "hub",
                "state": {"name": "My Hub"},
                "props": {},
            }
        }
        entity_cfg = EntityConfig(
            entity_type="binary_sensor",
            ha_name="",  # falsy — should not be added to kwargs
            hive_type="",  # falsy — should not be added to kwargs
            category=None,  # None — should not be added to kwargs
        )
        with patch("apyhiveapi.session.discovery.DEVICES", {"hub": [entity_cfg]}):
            result = await s.create_devices()
        # Should still process without error
        assert isinstance(result, dict)


class TestCreateDevicesDeviceAddListError:
    """Lines 232-233: KeyError/TypeError from add_list in DEVICES loop is caught."""

    async def test_add_list_keyerror_is_caught_not_raised(self):
        """KeyError from add_list during device processing is logged, not propagated."""
        s = _make_create_stub()
        s.data["devices"] = {
            "dev-1": {
                "id": "dev-1",
                "type": "hub",
                "state": {"name": "My Hub"},
                "props": {},
            }
        }
        entity_cfg = EntityConfig(
            entity_type="binary_sensor",
            ha_name="Hub Status",
            hive_type="Connectivity",
            category="diagnostic",
        )
        with patch("apyhiveapi.session.discovery.DEVICES", {"hub": [entity_cfg]}):
            with patch.object(s, "add_list", side_effect=KeyError("bad key")):
                # Should complete without raising
                result = await s.create_devices()
        assert isinstance(result, dict)

    async def test_add_list_typeerror_is_caught_not_raised(self):
        """TypeError from add_list during device processing is caught."""
        s = _make_create_stub()
        s.data["devices"] = {
            "dev-1": {
                "id": "dev-1",
                "type": "hub",
                "state": {"name": "My Hub"},
                "props": {},
            }
        }
        entity_cfg = EntityConfig(
            entity_type="binary_sensor",
            ha_name="",
            hive_type="",
            category=None,
        )
        with patch("apyhiveapi.session.discovery.DEVICES", {"hub": [entity_cfg]}):
            with patch.object(s, "add_list", side_effect=TypeError("bad type")):
                result = await s.create_devices()
        assert isinstance(result, dict)


class TestCreateDevicesActionAddListError:
    """Lines 258-259: KeyError/TypeError from add_list in actions loop is caught."""

    async def test_action_add_list_keyerror_is_caught(self):
        """KeyError from add_list when processing an action is logged, not propagated."""
        s = _make_create_stub()
        s.data["actions"] = {"act-1": {"id": "act-1", "name": "Good Night"}}
        with patch.object(s, "add_list", side_effect=KeyError("missing")):
            result = await s.create_devices()
        assert isinstance(result, dict)

    async def test_action_add_list_typeerror_is_caught(self):
        """TypeError from add_list when processing an action is caught."""
        s = _make_create_stub()
        s.data["actions"] = {"act-1": {"id": "act-1", "name": "Wake Up"}}
        with patch.object(s, "add_list", side_effect=TypeError("type error")):
            result = await s.create_devices()
        assert isinstance(result, dict)


class TestCreateDevicesProductTemperatureUnit:
    """Line 305: entity_config.temperature_unit is used when set and entity_type != 'climate'."""

    async def test_entity_config_temperature_unit_passed_to_add_list(self):
        """EntityConfig with temperature_unit set propagates that value as a kwarg."""
        s = _make_create_stub()
        s.data["products"] = {
            "prod-1": {
                "id": "prod-1",
                "type": "heating",
                "state": {"name": "Heating"},
                "props": {},
            }
        }
        # A non-climate entity with temperature_unit set triggers line 305
        entity_cfg = EntityConfig(
            entity_type="sensor",
            ha_name="Temp Sensor",
            hive_type="Current_Temperature",
            category="diagnostic",
            temperature_unit="F",
        )
        captured_kwargs = {}

        original_add_list = s.add_list

        def capturing_add_list(entity_type, data, **kwargs):
            captured_kwargs.update(kwargs)
            return original_add_list(entity_type, data, **kwargs)

        with patch("apyhiveapi.session.discovery.PRODUCTS", {"heating": [entity_cfg]}):
            with patch.object(s, "add_list", side_effect=capturing_add_list):
                await s.create_devices()

        assert captured_kwargs.get("temperature_unit") == "F"


class TestCreateDevicesProductAddListAttributeError:
    """Lines 308-309: NameError/AttributeError from add_list in products loop is caught."""

    async def test_product_add_list_attribute_error_is_caught(self):
        """AttributeError from add_list when processing a product is caught."""
        s = _make_create_stub()
        s.data["products"] = {
            "prod-1": {
                "id": "prod-1",
                "type": "heating",
                "state": {"name": "Heating"},
                "props": {},
            }
        }
        entity_cfg = EntityConfig(
            entity_type="climate",
            ha_name="",
            hive_type="",
            category=None,
        )
        with patch("apyhiveapi.session.discovery.PRODUCTS", {"heating": [entity_cfg]}):
            with patch.object(s, "add_list", side_effect=AttributeError("attr error")):
                result = await s.create_devices()
        assert isinstance(result, dict)

    async def test_product_add_list_name_error_is_caught(self):
        """NameError from add_list when processing a product is caught."""
        s = _make_create_stub()
        s.data["products"] = {
            "prod-1": {
                "id": "prod-1",
                "type": "heating",
                "state": {"name": "Heating"},
                "props": {},
            }
        }
        entity_cfg = EntityConfig(
            entity_type="climate",
            ha_name="",
            hive_type="",
            category=None,
        )
        with patch("apyhiveapi.session.discovery.PRODUCTS", {"heating": [entity_cfg]}):
            with patch.object(s, "add_list", side_effect=NameError("name error")):
                result = await s.create_devices()
        assert isinstance(result, dict)
