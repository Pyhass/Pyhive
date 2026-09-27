"""Unit tests for PollingMixin cache and rate-limit helpers."""

# pylint: disable=protected-access,attribute-defined-outside-init,too-few-public-methods

import asyncio
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.helper.hivedataclasses import Device
from apyhiveapi.session.polling import PollingMixin


def _make_device(ha_type="climate", hive_id="h1", hive_type="heating"):
    return Device(
        hive_id=hive_id,
        hive_name="T",
        hive_type=hive_type,
        ha_type=ha_type,
        device_id="d1",
        device_name="T",
        device_data={"online": True},
    )


def _make_polling():
    class StubPolling(PollingMixin):
        """Minimal concrete stub for testing PollingMixin."""

    p = StubPolling()
    p.entity_cache = {}
    p.update_lock = asyncio.Lock()
    p._update_task = None
    p._last_poll_slow = False
    p._slow_poll_threshold = 3
    return p


# ---------------------------------------------------------------------------
# _entity_cache_key
# ---------------------------------------------------------------------------


class TestEntityCacheKey:
    """Tests for PollingMixin._entity_cache_key."""

    def test_key_format(self):
        """Cache key is 'ha_type|hive_id|hive_type'."""
        p = _make_polling()
        d = _make_device(ha_type="climate", hive_id="h1", hive_type="heating")
        assert p._entity_cache_key(d) == "climate|h1|heating"

    def test_key_is_stable(self):
        """The same device always produces the same key."""
        p = _make_polling()
        d = _make_device()
        assert p._entity_cache_key(d) == p._entity_cache_key(d)

    def test_different_devices_produce_different_keys(self):
        """Two devices with different hive_ids produce distinct keys."""
        p = _make_polling()
        d1 = _make_device(hive_id="h1")
        d2 = _make_device(hive_id="h2")
        assert p._entity_cache_key(d1) != p._entity_cache_key(d2)

    def test_ha_type_included_in_key(self):
        """ha_type is part of the key — different ha_types yield different keys."""
        p = _make_polling()
        d1 = _make_device(ha_type="climate", hive_id="h1", hive_type="heating")
        d2 = _make_device(ha_type="sensor", hive_id="h1", hive_type="heating")
        assert p._entity_cache_key(d1) != p._entity_cache_key(d2)

    def test_key_is_string(self):
        """_entity_cache_key always returns a string."""
        p = _make_polling()
        d = _make_device()
        assert isinstance(p._entity_cache_key(d), str)

    def test_static_method_callable_on_class(self):
        """_entity_cache_key is a staticmethod — callable without an instance."""
        d = _make_device()
        assert PollingMixin._entity_cache_key(d) == "climate|h1|heating"


# ---------------------------------------------------------------------------
# Cache round-trip: set_cached_device / get_cached_device
# ---------------------------------------------------------------------------


class TestCacheRoundTrip:
    """Tests for PollingMixin.set_cached_device / get_cached_device."""

    def test_set_then_get_returns_device(self):
        """set then get returns the exact same device object."""
        p = _make_polling()
        d = _make_device()
        p.set_cached_device(d)
        assert p.get_cached_device(d) is d

    def test_get_unknown_returns_none(self):
        """get_cached_device returns None for a device not yet cached."""
        p = _make_polling()
        d = _make_device()
        assert p.get_cached_device(d) is None

    def test_set_returns_device(self):
        """set_cached_device returns the device it stores."""
        p = _make_polling()
        d = _make_device()
        assert p.set_cached_device(d) is d

    def test_overwrite_replaces_entry(self):
        """A second set_cached_device for the same key replaces the prior entry."""
        p = _make_polling()
        d1 = _make_device(hive_id="h1")
        d2 = _make_device(hive_id="h1")
        p.set_cached_device(d1)
        p.set_cached_device(d2)
        assert p.get_cached_device(d2) is d2

    def test_different_devices_cached_independently(self):
        """Distinct devices occupy separate cache slots."""
        p = _make_polling()
        d1 = _make_device(hive_id="h1")
        d2 = _make_device(hive_id="h2")
        p.set_cached_device(d1)
        p.set_cached_device(d2)
        assert p.get_cached_device(d1) is d1
        assert p.get_cached_device(d2) is d2

    def test_cache_populated_after_set(self):
        """entity_cache dict contains the key after set_cached_device."""
        p = _make_polling()
        d = _make_device()
        p.set_cached_device(d)
        key = p._entity_cache_key(d)
        assert key in p.entity_cache


# ---------------------------------------------------------------------------
# should_use_cached_data
# ---------------------------------------------------------------------------


class TestShouldUseCachedData:
    """Tests for PollingMixin.should_use_cached_data."""

    def test_last_poll_slow_returns_true(self):
        """True when _last_poll_slow is set."""
        p = _make_polling()
        p._last_poll_slow = True
        assert p.should_use_cached_data() is True

    def test_not_locked_not_slow_returns_false(self):
        """False when not slow and lock is not held."""
        p = _make_polling()
        assert p.should_use_cached_data() is False

    async def test_lock_held_without_update_task_returns_true(self):
        """True when update_lock is held and _update_task is None."""
        p = _make_polling()
        await p.update_lock.acquire()
        p._update_task = None
        result = p.should_use_cached_data()
        p.update_lock.release()
        assert result is True

    async def test_slow_poll_overrides_unlocked_state(self):
        """_last_poll_slow=True returns True even when lock is free."""
        p = _make_polling()
        p._last_poll_slow = True
        assert p.should_use_cached_data() is True

    async def test_lock_held_by_update_task_itself_returns_false(self):
        """False when update_lock is locked *and* current task is _update_task."""
        p = _make_polling()

        async def _hold_lock():
            async with p.update_lock:
                p._update_task = asyncio.current_task()
                return p.should_use_cached_data()

        result = await _hold_lock()
        assert result is False


# ---------------------------------------------------------------------------
# _poll_devices
# ---------------------------------------------------------------------------


class TestPollDevices:
    """Tests for PollingMixin._poll_devices."""

    async def test_poll_devices_delegates_to_get_devices(self):
        """_poll_devices calls get_devices('No_ID') and returns its result."""
        p = _make_polling()
        p.get_devices = AsyncMock(return_value=True)
        result = await p._poll_devices()
        p.get_devices.assert_awaited_once_with("No_ID")
        assert result is True

    async def test_poll_devices_propagates_false(self):
        """_poll_devices returns False when get_devices returns False."""
        p = _make_polling()
        p.get_devices = AsyncMock(return_value=False)
        result = await p._poll_devices()
        assert result is False


# ---------------------------------------------------------------------------
# TestGetDevicesSlowPoll
# ---------------------------------------------------------------------------


class TestGetDevicesSlowPoll:
    async def test_auth_error_sets_last_poll_slow_false(self):
        from apyhiveapi.helper.hive_exceptions import HiveAuthError

        p = _make_polling()
        p.api = MagicMock()
        p.api.get_all = AsyncMock(side_effect=HiveAuthError())
        p.config = MagicMock()
        p.config.file = False
        p.tokens = MagicMock()
        p._last_poll_slow = True  # pre-set to True to confirm it gets cleared

        retry_result = {
            "original": 200,
            "parsed": {"products": [], "devices": [], "actions": []},
        }

        async def fake_retry_login():
            pass

        async def fake_retry_with_backoff(_fn, **_kwargs):
            return retry_result

        p._retry_login = fake_retry_login
        p._retry_with_backoff = fake_retry_with_backoff
        p.hive_refresh_tokens = AsyncMock()
        p.data = MagicMock()
        p.data.products = {}
        p.data.devices = {}
        p.data.actions = {}
        p.config.last_update = MagicMock()
        p.config.scan_interval = MagicMock()

        await p.get_devices("No_ID")
        assert p._last_poll_slow is False

    async def test_tokens_none_returns_false_without_crash(self):
        """get_devices returns False (no crash) when tokens=None and file=False."""
        from apyhiveapi.helper.map import Map

        p = _make_polling()
        p.config = MagicMock()
        p.config.file = False
        p.tokens = None  # triggers the "neither branch" path
        p.data = Map({"products": {}, "devices": {}, "actions": {}, "user": {}})

        result = await p.get_devices("No_ID")
        assert result is False

    async def test_slow_api_call_sets_last_poll_slow_true(self):
        p = _make_polling()
        p._slow_poll_threshold = 0  # any call will be "slow"
        p.api = MagicMock()

        slow_result = {
            "original": 200,
            "parsed": {"products": [], "devices": [], "actions": []},
        }

        async def slow_get_all():
            return slow_result

        p.api.get_all = slow_get_all
        p.config = MagicMock()
        p.config.file = False
        p.tokens = MagicMock()
        p.hive_refresh_tokens = AsyncMock()
        p.data = MagicMock()
        p.data.products = {}
        p.data.devices = {}
        p.data.actions = {}
        p.config.last_update = MagicMock()
        p.config.scan_interval = MagicMock()

        await p.get_devices("No_ID")
        assert p._last_poll_slow is True


# ---------------------------------------------------------------------------
# TestGetDevicesNoneGuard — api.get_all() returning None must not crash
# ---------------------------------------------------------------------------


class TestGetDevicesNoneGuard:
    """api_resp_d must be guarded before dict access when api.get_all() returns None."""

    async def test_api_returns_none_does_not_crash(self):
        """get_devices returns False without crashing when api.get_all() returns None."""
        from apyhiveapi.helper.map import Map

        p = _make_polling()
        p.config = MagicMock()
        p.config.file = False
        p.tokens = MagicMock()
        p.api = MagicMock()
        p.api.get_all = AsyncMock(return_value=None)
        p.hive_refresh_tokens = AsyncMock()
        p.data = Map({"products": {}, "devices": {}, "actions": {}, "user": {}})

        result = await p.get_devices("No_ID")
        assert result is False


# ---------------------------------------------------------------------------
# TestGetDevicesHomesKey — homes list null/empty must not crash
# ---------------------------------------------------------------------------


class TestGetDevicesHomesKey:
    """homes key in API response must not crash when homes list is None or empty."""

    async def _run_get_devices_with_parsed(self, parsed):
        from apyhiveapi.helper.map import Map

        p = _make_polling()
        p.config = MagicMock()
        p.config.file = False
        p.tokens = MagicMock()
        p.api = MagicMock()
        p.api.get_all = AsyncMock(return_value={"original": "200", "parsed": parsed})
        p.hive_refresh_tokens = AsyncMock()
        p.data = Map({"products": {}, "devices": {}, "actions": {}, "user": {}})
        return p, await p.get_devices("No_ID")

    async def test_homes_null_does_not_crash(self):
        """No crash when API returns homes.homes = None."""
        parsed = {
            "products": [],
            "devices": [],
            "actions": [],
            "homes": {"homes": None},
        }
        _p, result = await self._run_get_devices_with_parsed(parsed)
        assert isinstance(result, bool)

    async def test_homes_empty_list_does_not_crash(self):
        """No crash when API returns homes.homes = []."""
        parsed = {"products": [], "devices": [], "actions": [], "homes": {"homes": []}}
        _p, result = await self._run_get_devices_with_parsed(parsed)
        assert isinstance(result, bool)

    async def test_valid_homes_list_sets_home_id(self):
        """home_id is set correctly from a valid homes list."""
        parsed = {
            "products": [],
            "devices": [],
            "actions": [],
            "homes": {"homes": [{"id": "home-abc"}]},
        }
        p, _ = await self._run_get_devices_with_parsed(parsed)
        assert p.config.home_id == "home-abc"

    async def test_homes_data_not_dict_does_not_crash(self):
        """No crash when homes_data is a non-dict (list); home_id stays unset."""
        parsed = {
            "products": [],
            "devices": [],
            "actions": [],
            "homes": [{"id": "home-list"}],
        }
        _p, result = await self._run_get_devices_with_parsed(parsed)
        assert isinstance(result, bool)
