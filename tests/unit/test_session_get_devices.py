"""Branch-coverage tests for PollingMixin.get_devices and update_data edge cases."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveAuthError,
    HiveReauthRequired,
)
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map
from apyhiveapi.session.polling import PollingMixin

_FAR_PAST = timedelta(seconds=9999)


def _make_stub():
    """Return a PollingMixin stub with all external dependencies mocked."""

    class StubPolling(PollingMixin):
        """Concrete subclass used only for testing."""

    p = StubPolling()
    p.config = SessionConfig()
    p.config.last_update = datetime.now() - _FAR_PAST
    p.data = Map(
        {"products": {}, "devices": {}, "actions": {}, "minMax": {}, "user": {}}
    )
    p.tokens = None
    p.entity_cache = {}
    p.update_lock = asyncio.Lock()
    p._update_task = None
    p._last_poll_slow = False
    p._slow_poll_threshold = 3

    # External dependencies (provided by HiveSession in real code)
    p.api = MagicMock()
    p.api.get_all = AsyncMock(
        return_value={"original": 200, "parsed": {"user": {"id": "u1"}}}
    )
    p.hive_refresh_tokens = AsyncMock()
    p._retry_login = AsyncMock()
    p._retry_with_backoff = AsyncMock(
        return_value={"original": 200, "parsed": {"user": {"id": "u1"}}}
    )
    p.open_file = MagicMock(
        return_value={"original": 200, "parsed": {"user": {"id": "u1"}}}
    )
    return p


def _make_device():
    return Device(
        hive_id="prod-1",
        hive_name="Test",
        hive_type="heating",
        ha_type="climate",
        device_id="dev-1",
        device_name="Test",
        device_data={"online": True},
    )


# ---------------------------------------------------------------------------
# get_devices — file mode
# ---------------------------------------------------------------------------


class TestGetDevicesFileMode:
    """Tests for get_devices when config.file is True."""

    async def test_file_mode_loads_from_file_and_succeeds(self):
        """File mode calls open_file and processes the returned data."""
        p = _make_stub()
        p.config.file = True
        p.open_file.return_value = {
            "original": 200,
            "parsed": {"user": {"id": "file-user"}},
        }
        result = await p.get_devices("No_ID")
        p.open_file.assert_called_once_with("data.json")
        assert result is True
        assert p.data.user["id"] == "file-user"

    async def test_file_mode_does_not_call_api(self):
        """File mode never touches the API layer."""
        p = _make_stub()
        p.config.file = True
        await p.get_devices("No_ID")
        p.api.get_all.assert_not_called()
        p.hive_refresh_tokens.assert_not_called()


# ---------------------------------------------------------------------------
# get_devices — malformed API responses
# ---------------------------------------------------------------------------


class TestGetDevicesMalformedResponse:
    """Hostile/partial response shapes must not escape as raw KeyError."""

    async def test_user_without_id_still_succeeds(self):
        """A user object with no 'id' key must not crash the poll."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all = AsyncMock(
            return_value={"original": 200, "parsed": {"user": {"name": "x"}}}
        )
        result = await p.get_devices("No_ID")
        assert result is True
        assert p.config.user_id is None

    async def test_product_without_id_returns_false(self):
        """A product entry with no 'id' key fails the poll gracefully."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all = AsyncMock(
            return_value={
                "original": 200,
                "parsed": {"products": [{"type": "heating"}]},
            }
        )
        result = await p.get_devices("No_ID")
        assert result is False


# ---------------------------------------------------------------------------
# get_devices — tokens path
# ---------------------------------------------------------------------------


class TestGetDevicesTokensPath:
    """Tests for get_devices when tokens is not None."""

    async def test_tokens_path_successful_returns_true(self):
        """Normal tokens path with 200 response returns True."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.return_value = {
            "original": 200,
            "parsed": {"user": {"id": "u1"}},
        }
        result = await p.get_devices("No_ID")
        assert result is True
        p.hive_refresh_tokens.assert_called_once()

    async def test_slow_api_call_sets_last_poll_slow(self):
        """API call taking longer than threshold sets _last_poll_slow = True."""
        p = _make_stub()
        p.tokens = MagicMock()
        p._slow_poll_threshold = 0  # every call is "slow"
        p.api.get_all.return_value = {
            "original": 200,
            "parsed": {"user": {"id": "u1"}},
        }
        await p.get_devices("No_ID")
        assert p._last_poll_slow is True

    async def test_fast_api_call_clears_last_poll_slow(self):
        """API call faster than threshold sets _last_poll_slow = False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p._last_poll_slow = True  # start as slow
        p._slow_poll_threshold = 9999  # nothing is slow
        p.api.get_all.return_value = {
            "original": 200,
            "parsed": {"user": {"id": "u1"}},
        }
        await p.get_devices("No_ID")
        assert p._last_poll_slow is False

    async def test_non_2xx_response_raises_http_exception_returns_false(self):
        """A non-2xx 'original' response code causes get_devices to return False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.return_value = {"original": 400, "parsed": {"user": {"id": "u1"}}}
        result = await p.get_devices("No_ID")
        assert result is False

    async def test_parsed_none_raises_hive_api_error_returns_false(self):
        """parsed=None causes HiveApiError internally; get_devices returns False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.return_value = {"original": 200, "parsed": None}
        result = await p.get_devices("No_ID")
        assert result is False

    async def test_hive_auth_error_triggers_retry_and_continues(self):
        """HiveAuthError from api.get_all triggers _retry_login then _retry_with_backoff."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.side_effect = HiveAuthError()
        p._retry_with_backoff.return_value = {
            "original": 200,
            "parsed": {"user": {"id": "retry-user"}},
        }
        result = await p.get_devices("No_ID")
        p._retry_login.assert_called_once()
        p._retry_with_backoff.assert_called_once()
        assert result is True


# ---------------------------------------------------------------------------
# get_devices — tokens is None
# ---------------------------------------------------------------------------


class TestGetDevicesTokensNone:
    """Tests for get_devices when tokens is None and file mode is off."""

    async def test_tokens_none_returns_false(self):
        """With no tokens and no file mode, get_devices returns False immediately."""
        p = _make_stub()
        p.tokens = None
        p.config.file = False
        result = await p.get_devices("No_ID")
        assert result is False
        p.api.get_all.assert_not_called()


# ---------------------------------------------------------------------------
# get_devices — data parsing
# ---------------------------------------------------------------------------


class TestGetDevicesDataParsing:
    """Tests for get_devices data-parsing branches."""

    async def _run_with_parsed(self, parsed: dict):
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.return_value = {"original": 200, "parsed": parsed}
        await p.get_devices("No_ID")
        return p

    async def test_user_data_parsed_sets_user_and_user_id(self):
        """'user' key in parsed response sets data.user and config.user_id."""
        p = await self._run_with_parsed({"user": {"id": "my-user"}})
        assert p.data.user["id"] == "my-user"
        assert p.config.user_id == "my-user"

    async def test_products_parsed_populates_data_products(self):
        """'products' list in parsed response populates data.products."""
        p = await self._run_with_parsed({"products": [{"id": "p1", "type": "heating"}]})
        assert "p1" in p.data.products

    async def test_devices_parsed_populates_data_devices(self):
        """'devices' list in parsed response populates data.devices."""
        p = await self._run_with_parsed({"devices": [{"id": "d1", "type": "hub"}]})
        assert "d1" in p.data.devices

    async def test_homes_parsed_sets_config_home_id(self):
        """'homes' key sets config.home_id from the first entry."""
        p = await self._run_with_parsed({"homes": {"homes": [{"id": "home-123"}]}})
        assert p.config.home_id == "home-123"

    async def test_actions_parsed_populates_data_actions(self):
        """'actions' list in parsed response populates data.actions."""
        p = await self._run_with_parsed({"actions": [{"id": "act-1"}]})
        assert "act-1" in p.data.actions


# ---------------------------------------------------------------------------
# get_devices — exception handling
# ---------------------------------------------------------------------------


class TestGetDevicesExceptions:
    """Tests for get_devices exception-handling branches."""

    async def test_hive_reauth_required_propagates(self):
        """HiveReauthRequired from api.get_all propagates to the caller."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.side_effect = HiveReauthRequired()
        with pytest.raises(HiveReauthRequired):
            await p.get_devices("No_ID")

    async def test_timeout_error_marks_slow_and_returns_false(self):
        """asyncio.TimeoutError sets _last_poll_slow=True and returns False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.side_effect = asyncio.TimeoutError()
        result = await p.get_devices("No_ID")
        assert result is False
        assert p._last_poll_slow is True

    async def test_os_error_returns_false(self):
        """OSError during api.get_all causes get_devices to return False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.side_effect = OSError("network gone")
        result = await p.get_devices("No_ID")
        assert result is False

    async def test_runtime_error_returns_false(self):
        """RuntimeError during api.get_all causes get_devices to return False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.side_effect = RuntimeError("unexpected")
        result = await p.get_devices("No_ID")
        assert result is False

    async def test_connection_error_returns_false(self):
        """ConnectionError during api.get_all causes get_devices to return False."""
        p = _make_stub()
        p.tokens = MagicMock()
        p.api.get_all.side_effect = ConnectionError("connection refused")
        result = await p.get_devices("No_ID")
        assert result is False


# ---------------------------------------------------------------------------
# update_data — lock re-check branch
# ---------------------------------------------------------------------------


class TestUpdateDataExtended:
    """Tests for update_data branches not covered by the main polling test file."""

    async def test_fresh_after_acquiring_lock_skips_poll(self):
        """After acquiring the update_lock, if last_update is now fresh, poll is skipped."""
        p = _make_stub()
        p.config.last_update = datetime.now() - _FAR_PAST  # stale initially
        p._poll_devices = AsyncMock(return_value=True)

        # Acquire the lock ourselves so update_data blocks until we release it
        await p.update_lock.acquire()

        async def _refresh_and_release():
            await asyncio.sleep(0)
            # Make last_update appear fresh before releasing lock
            p.config.last_update = datetime.now()
            p.update_lock.release()

        release_task = asyncio.create_task(_refresh_and_release())
        result = await p.update_data(_make_device())
        await release_task

        # Because the re-check inside the lock saw a fresh last_update, poll was skipped
        p._poll_devices.assert_not_called()
        assert result is False

    async def test_update_task_set_to_current_during_poll(self):
        """During polling, _update_task is set to the running task."""
        p = _make_stub()
        captured = []

        async def _capture_task():
            captured.append(p._update_task)
            return True

        p._poll_devices = _capture_task
        await p.update_data(_make_device())
        # After completion, _update_task is cleared
        assert p._update_task is None
        # During execution, it was set to a Task instance
        assert len(captured) == 1
        assert captured[0] is not None

    async def test_inner_recheck_returns_early_via_mocked_clock(self):
        """Line 99: inner re-check sees fresh ep and returns early without polling.

        Strategy: patch datetime.now so the outer check passes (time appears
        past ep) but the inner check sees a time *before* ep (mocking the
        scenario where another task updated last_update between the two checks).
        """
        p = _make_stub()
        p._poll_devices = AsyncMock(return_value=True)

        # Fix a reference point: last_update two minutes ago, 60s scan interval
        anchor = datetime(2020, 1, 1, 12, 0, 0)
        p.config.last_update = anchor
        p.config.scan_interval = timedelta(seconds=60)
        # ep = 12:01:00

        call_count = 0

        def mock_now():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Outer check: return a time past ep so outer if passes
                return datetime(2020, 1, 1, 12, 2, 0)
            # Inner re-check: return a time before ep so if at line 98 is True
            return datetime(2020, 1, 1, 12, 0, 30)

        with patch("apyhiveapi.session.polling.datetime") as mock_dt:
            mock_dt.now = mock_now
            result = await p.update_data(_make_device())

        # Returned early at line 99 — no poll
        p._poll_devices.assert_not_called()
        assert result is False

    async def test_update_task_changed_during_poll_skips_reset_in_finally(self):
        """Lines 113->116: when _update_task is replaced during _poll_devices,
        the finally block does NOT reset it (False branch of the is-check).

        Uses a sentinel object so the branch fires on every Python version —
        on Python 3.10, asyncio.current_task() can be None inside
        run_until_complete(), which would make ``None is None`` evaluate to
        True and skip the False branch if we set _update_task to None instead.
        """
        p = _make_stub()
        p.config.last_update = datetime.now() - _FAR_PAST
        p.config.scan_interval = timedelta(seconds=60)

        sentinel = object()

        async def poll_that_replaces_task():
            # Simulate another coroutine taking ownership of _update_task
            p._update_task = sentinel
            return True

        p._poll_devices = poll_that_replaces_task
        result = await p.update_data(_make_device())

        assert result is True
        # finally block left _update_task alone because it no longer matched
        # current_task (the False branch — line 113->116)
        assert p._update_task is sentinel
