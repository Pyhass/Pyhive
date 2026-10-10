"""Tests for HiveAction."""

# pylint: disable=protected-access
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.action import HiveAction
from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.helper.map import Map

HTTP_200 = 200
HTTP_500 = 500


def _make_action(actions=None):
    """Build a HiveAction with a mocked session."""
    session = MagicMock()
    session.data = Map(
        {
            "products": {},
            "devices": {},
            "actions": actions or {},
            "minMax": {},
            "user": {},
        }
    )
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.api = MagicMock()
    session.api.set_action = AsyncMock(
        return_value={"original": HTTP_200, "parsed": {}}
    )
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return HiveAction(session=session)


def _make_device(hive_id="action-1"):
    """Return a minimal action Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Good Night",
        hive_type="action",
        ha_type="switch",
        device_id="action-1",
        device_name="Good Night",
        device_data={},
        ha_name="Good Night",
    )


class TestGetState:
    """Tests for HiveAction.get_state."""

    async def test_returns_enabled_value(self):
        """get_state returns True when the action is enabled."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": True}}
        )
        assert await action.get_state(_make_device()) is True

    async def test_disabled_returns_false(self):
        """get_state returns False when the action is disabled."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": False}}
        )
        assert await action.get_state(_make_device()) is False

    async def test_missing_key_returns_none(self):
        """get_state returns None when the hive_id is not in actions."""
        action = _make_action({})
        assert await action.get_state(_make_device()) is None


class TestGetAction:
    """Tests for HiveAction.get_action."""

    async def test_in_actions_populates_status(self):
        """get_action returns the device with status set when id is present."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": True}}
        )
        d = _make_device()
        result = await action.get_action(d)
        assert result.status == {"state": True}

    async def test_not_in_actions_returns_remove(self):
        """get_action returns 'REMOVE' when hive_id is not found in actions."""
        action = _make_action({})
        result = await action.get_action(_make_device())
        assert result == "REMOVE"

    async def test_cached_returns_cached(self):
        """get_action returns cached device when should_use_cached_data is True."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": True}}
        )
        cached_device = _make_device()
        action.session.should_use_cached_data.return_value = True
        action.session.get_cached_device.return_value = cached_device
        result = await action.get_action(_make_device())
        assert result is cached_device


class TestSetActionState:
    """Tests for HiveAction._set_action_state."""

    async def test_http_200_returns_true(self):
        """_set_action_state returns True and calls get_devices on HTTP 200."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": False}}
        )
        assert await action._set_action_state(_make_device(), True) is True  # noqa: SLF001
        action.session.get_devices.assert_called_once()

    async def test_non_200_returns_false(self):
        """_set_action_state returns False when the API returns a non-200 status."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": False}}
        )
        action.session.api.set_action.return_value = {
            "original": HTTP_500,
            "parsed": {},
        }
        assert await action._set_action_state(_make_device(), True) is False  # noqa: SLF001

    async def test_not_in_actions_returns_false(self):
        """_set_action_state returns False without calling the API when id is absent."""
        action = _make_action({})
        assert await action._set_action_state(_make_device(), True) is False  # noqa: SLF001


class TestSetStatusOnOff:
    """Tests for HiveAction.set_status_on and set_status_off."""

    async def test_set_status_on_calls_set_action_state_true(self):
        """set_status_on delegates to _set_action_state with enabled=True."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": False}}
        )
        result = await action.set_status_on(_make_device())
        assert result is True

    async def test_set_status_off_calls_set_action_state_false(self):
        """set_status_off delegates to _set_action_state with enabled=False."""
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": True}}
        )
        result = await action.set_status_off(_make_device())
        assert result is True
