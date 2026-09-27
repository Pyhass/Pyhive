"""Unit tests for Device, SessionTokens, and SessionConfig dataclasses."""

from datetime import datetime, timedelta

import pytest
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig, SessionTokens

# Test constants
DEFAULT_MAGIC_VALUE = 42


def _make_device(**kwargs):
    """Create a Device with sensible defaults for testing."""
    defaults = {
        "hive_id": "h1",
        "hive_name": "Test",
        "hive_type": "heating",
        "ha_type": "climate",
        "device_id": "d1",
        "device_name": "Test",
        "device_data": {"online": True},
    }
    defaults.update(kwargs)
    return Device(**defaults)


class TestDevice:
    """Tests for Device dataclass."""

    def test_dict_read_snake_case(self):
        """Test reading device attribute using snake_case key."""
        d = _make_device(hive_id="abc")
        assert d["hive_id"] == "abc"

    def test_dict_read_camel_case_translated(self):
        """Test reading device attribute using legacy camelCase key."""
        d = _make_device(hive_id="abc")
        assert d["hiveID"] == "abc"

    def test_dict_write_camel_case(self):
        """Test writing device attribute using legacy camelCase key."""
        d = _make_device()
        d["hiveID"] = "xyz"
        assert d.hive_id == "xyz"

    def test_contains_present_key(self):
        """Test __contains__ returns True for present non-None key."""
        d = _make_device(hive_id="h1")
        assert "hive_id" in d

    def test_contains_none_value_is_false(self):
        """Test __contains__ returns False for None values."""
        d = _make_device(parent_device=None)
        assert "parent_device" not in d

    def test_contains_missing_key_is_false(self):
        """Test __contains__ returns False for missing keys."""
        d = _make_device()
        assert "nonexistent" not in d

    def test_get_returns_value(self):
        """Test get() returns value when key exists."""
        d = _make_device(hive_id="h1")
        assert d.get("hive_id") == "h1"

    def test_get_returns_default_for_none(self):
        """Test get() returns default when value is None."""
        d = _make_device(parent_device=None)
        assert d.get("parent_device", "fallback") == "fallback"

    def test_get_returns_default_for_missing(self):
        """Test get() returns default for missing keys."""
        d = _make_device()
        assert d.get("nonexistent", DEFAULT_MAGIC_VALUE) == DEFAULT_MAGIC_VALUE

    def test_missing_key_raises_keyerror(self):
        """Test __getitem__ raises KeyError for unknown keys."""
        d = _make_device()
        with pytest.raises(KeyError):
            _ = d["totally_unknown_key"]


class TestSessionTokens:
    """Tests for SessionTokens dataclass."""

    def test_default_token_data_is_empty_dict(self):
        """Test token_data defaults to empty dict."""
        t = SessionTokens()
        assert t.token_data == {}

    def test_default_token_created_is_datetime_min(self):
        """Test token_created defaults to datetime.min."""
        t = SessionTokens()
        assert t.token_created == datetime.min

    def test_default_token_expiry_is_one_hour(self):
        """Test token_expiry defaults to 3600 seconds."""
        t = SessionTokens()
        assert t.token_expiry == timedelta(seconds=3600)


class TestSessionConfig:
    """Tests for SessionConfig dataclass."""

    def test_default_file_is_false(self):
        """Test file defaults to False."""
        c = SessionConfig()
        assert c.file is False

    def test_default_scan_interval_is_120s(self):
        """Test scan_interval defaults to 120 seconds."""
        c = SessionConfig()
        assert c.scan_interval == timedelta(seconds=120)

    def test_default_battery_is_empty_set(self):
        """Test battery defaults to empty set."""
        c = SessionConfig()
        assert c.battery == set()

    def test_username_stored(self):
        """Test username can be set and retrieved."""
        c = SessionConfig(username="user@example.com")
        assert c.username == "user@example.com"


class TestSessionConfigCollectionTypes:
    """battery and mode must be sets for O(1) membership checks."""

    def test_battery_is_set(self):
        """SessionConfig.battery is a set (not a list)."""
        config = SessionConfig()
        assert isinstance(config.battery, set), (
            f"Expected set, got {type(config.battery).__name__}"
        )

    def test_mode_is_set(self):
        """SessionConfig.mode is a set (not a list)."""
        config = SessionConfig()
        assert isinstance(config.mode, set), (
            f"Expected set, got {type(config.mode).__name__}"
        )

    def test_battery_supports_membership_check(self):
        """Can check membership in battery using 'in' after add."""
        config = SessionConfig()
        config.battery.add("d1")
        assert "d1" in config.battery

    def test_mode_supports_membership_check(self):
        """Can check membership in mode using 'in' after add."""
        config = SessionConfig()
        config.mode.add("p1")
        assert "p1" in config.mode
