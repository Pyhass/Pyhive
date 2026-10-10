"""Additional HiveAction tests covering branch 43->49.

Branch 43->49: should_use_cached_data() is True but get_cached_device()
returns None, so execution falls through from the cache block (line 43)
to the main lookup at line 49.
"""

from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.action import HiveAction
from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.helper.map import Map

HTTP_200 = 200


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
    session.should_use_cached_data = MagicMock(return_value=True)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return HiveAction(session=session)


def _make_device(hive_id="action-1"):
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


class TestGetActionCacheMissFallthrough:
    """Covers branch 43->49: cache path entered but cache miss, falls through."""

    async def test_cache_miss_falls_through_to_actions_lookup(self):
        """When should_use_cached_data is True but cache returns None,
        get_action proceeds to the actions dict lookup (line 49) and
        returns the device with status populated.

        This is the branch 43->49 path.
        """
        action = _make_action(
            {"action-1": {"id": "action-1", "name": "GN", "enabled": True}}
        )
        d = _make_device()
        result = await action.get_action(d)
        # Cache was checked but missed, so the normal data path ran
        action.session.get_cached_device.assert_called_once_with(d)
        assert result.status == {"state": True}

    async def test_cache_miss_falls_through_returns_remove_when_not_in_actions(self):
        """When cache miss and hive_id not in actions, returns 'REMOVE'."""
        action = _make_action({})  # empty actions
        d = _make_device()
        result = await action.get_action(d)
        assert result == "REMOVE"
