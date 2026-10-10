"""Unit tests for DiscoveryMixin."""

# pylint: disable=protected-access,attribute-defined-outside-init

from unittest.mock import MagicMock

from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map
from apyhiveapi.session.discovery import DiscoveryMixin


def _make_discovery():
    class StubDiscovery(DiscoveryMixin):  # pylint: disable=too-few-public-methods
        """Minimal concrete stub for testing DiscoveryMixin."""

    d = StubDiscovery()
    d.config = SessionConfig()  # type: ignore[attr-defined]
    d.data = Map(  # type: ignore[attr-defined]
        {
            "products": {},
            "devices": {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    d.helper = MagicMock()  # type: ignore[attr-defined]
    d.helper.get_device_data = MagicMock(
        return_value={
            "id": "dev-1",
            "state": {"name": "Living Room"},
            "props": {"online": True},
        }
    )
    d.hub_id = "hub-1"  # type: ignore[attr-defined]
    d.device_list = {  # type: ignore[attr-defined]
        "parent": [],
        "binary_sensor": [],
        "climate": [],
        "light": [],
        "sensor": [],
        "switch": [],
        "water_heater": [],
    }
    return d


# ---------------------------------------------------------------------------
# open_file
# ---------------------------------------------------------------------------


class TestOpenFile:
    """Tests for DiscoveryMixin.open_file."""

    def test_returns_dict(self):
        """open_file returns a dict for data.json."""
        d = _make_discovery()
        result = d.open_file("data.json")
        assert isinstance(result, dict)

    def test_has_original_key(self):
        """data.json has a top-level 'original' key."""
        d = _make_discovery()
        result = d.open_file("data.json")
        assert "original" in result

    def test_has_parsed_key(self):
        """data.json has a top-level 'parsed' key."""
        d = _make_discovery()
        result = d.open_file("data.json")
        assert "parsed" in result

    def test_parsed_value_is_dict_or_none(self):
        """The 'parsed' value is either a dict or None — not an unexpected type."""
        d = _make_discovery()
        result = d.open_file("data.json")
        assert result["parsed"] is None or isinstance(result["parsed"], dict)


# ---------------------------------------------------------------------------
# _configure_file_mode
# ---------------------------------------------------------------------------


class TestConfigureFileMode:
    """Tests for DiscoveryMixin._configure_file_mode."""

    def test_magic_username_sets_file_true(self):
        """The magic testing username 'use@file.com' enables file mode."""
        d = _make_discovery()
        d._configure_file_mode("use@file.com")
        assert d.config.file is True

    def test_other_username_leaves_file_false(self):
        """A real username does not enable file mode."""
        d = _make_discovery()
        d._configure_file_mode("real@user.com")
        assert d.config.file is False

    def test_none_username_leaves_file_false(self):
        """None username does not enable file mode."""
        d = _make_discovery()
        d._configure_file_mode(None)
        assert d.config.file is False

    def test_empty_string_leaves_file_false(self):
        """Empty string username does not enable file mode."""
        d = _make_discovery()
        d._configure_file_mode("")
        assert d.config.file is False


# ---------------------------------------------------------------------------
# add_list
# ---------------------------------------------------------------------------


class TestAddList:
    """Tests for DiscoveryMixin.add_list."""

    def test_action_path_creates_device_with_action_type(self):
        """hive_type='action' creates a Device with hive_type='action'."""
        d = _make_discovery()
        data = {"id": "action-1", "name": "Good Night"}
        device = d.add_list("switch", data, hive_type="action", ha_name="Good Night")
        assert device is not None
        assert device.hive_type == "action"
        assert device in d.device_list["switch"]

    def test_action_device_not_added_to_parent(self):
        """Action devices are not added to the 'parent' list."""
        d = _make_discovery()
        data = {"id": "action-1", "name": "Good Night"}
        d.add_list("switch", data, hive_type="action", ha_name="Good Night")
        assert len(d.device_list["parent"]) == 0

    def test_normal_path_creates_device_with_name_from_state(self):
        """Non-action device gets its name from the device state."""
        d = _make_discovery()
        data = {"id": "heat-1", "type": "heating"}
        device = d.add_list("climate", data)
        assert device is not None
        assert device.hive_name == "Living Room"

    def test_normal_path_appends_to_entity_list(self):
        """Created device is appended to the correct entity-type list."""
        d = _make_discovery()
        data = {"id": "heat-1", "type": "heating"}
        device = d.add_list("climate", data)
        assert device in d.device_list["climate"]

    def test_receiver_name_becomes_heating(self):
        """A device state name of 'Receiver' is remapped to 'Heating'."""
        d = _make_discovery()
        d.helper.get_device_data.return_value = {
            "id": "dev-1",
            "state": {"name": "Receiver"},
            "props": {},
        }
        data = {"id": "heat-1", "type": "heating"}
        device = d.add_list("climate", data)
        assert device.hive_name == "Heating"

    def test_ha_name_space_prefix_prepends_device_name(self):
        """ha_name starting with a space gets device name prepended."""
        d = _make_discovery()
        data = {"id": "p1", "type": "heating"}
        device = d.add_list("sensor", data, ha_name=" Current Temperature")
        assert device.ha_name == "Living Room Current Temperature"

    def test_ha_name_no_prefix_used_as_is(self):
        """ha_name not starting with a space is used verbatim."""
        d = _make_discovery()
        data = {"id": "p1", "type": "heating"}
        device = d.add_list("sensor", data, ha_name="My Sensor")
        assert device.ha_name == "My Sensor"

    def test_no_ha_name_kwarg_uses_device_name(self):
        """When ha_name is not supplied, ha_name defaults to device name."""
        d = _make_discovery()
        data = {"id": "p1", "type": "heating"}
        device = d.add_list("climate", data)
        assert device.ha_name == "Living Room"

    def test_missing_key_returns_none(self):
        """A KeyError from get_device_data causes add_list to return None."""
        d = _make_discovery()
        d.helper.get_device_data.side_effect = KeyError("id")
        result = d.add_list("climate", {"id": "bad"})
        assert result is None

    def test_action_ha_name_from_kwarg(self):
        """Action device ha_name comes from the ha_name kwarg."""
        d = _make_discovery()
        data = {"id": "a-1", "name": "Ignored Name"}
        device = d.add_list("switch", data, hive_type="action", ha_name="Night Mode")
        assert device.ha_name == "Night Mode"

    def test_hub_type_also_added_to_parent(self):
        """Devices with type='hub' are added to device_list['parent'] as well."""
        d = _make_discovery()
        d.helper.get_device_data.return_value = {
            "id": "hub-device",
            "state": {"name": "Hive Hub"},
            "props": {"online": True},
        }
        data = {"id": "hub-device", "type": "hub"}
        device = d.add_list("binary_sensor", data)
        assert device in d.device_list["parent"]
        assert device in d.device_list["binary_sensor"]

    def test_returns_device_instance(self):
        """add_list returns the created Device object."""
        d = _make_discovery()
        data = {"id": "heat-1", "type": "heating"}
        device = d.add_list("climate", data)
        assert isinstance(device, Device)
