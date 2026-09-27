"""File-mode integration tests and unit tests for session utilities."""

# pylint: disable=redefined-outer-name

from unittest.mock import AsyncMock, patch

import pytest
from apyhiveapi import Hive
from apyhiveapi.helper.hive_helper import HiveHelper


class TestFileSession:
    """Integration tests using the bundled data.json file fixture."""

    async def test_start_session_returns_devices(self, file_session):
        """start_session populates device_list with entries from the fixture."""
        dl = file_session.device_list
        assert dl, "device_list should not be empty"

    async def test_climate_devices_present(self, file_session):
        """Fixture contains heating products — climate entries should exist."""
        assert file_session.device_list.get("climate"), "expected climate devices"

    async def test_light_devices_present(self, file_session):
        """Fixture contains light products — light entries should exist."""
        assert file_session.device_list.get("light"), "expected light devices"

    async def test_switch_devices_present(self, file_session):
        """Fixture contains switch products — switch entries should exist."""
        assert file_session.device_list.get("switch"), "expected switch devices"

    async def test_water_heater_devices_present(self, file_session):
        """Fixture contains hot water products — water_heater entries should exist."""
        assert file_session.device_list.get("water_heater"), "expected water_heater"

    async def test_binary_sensor_devices_present(self, file_session):
        """Fixture contains sensor products — binary_sensor entries should exist."""
        assert file_session.device_list.get("binary_sensor"), "expected binary_sensor"

    async def test_get_climate_returns_status(self, file_session):
        """get_climate populates device.status with required heating fields."""
        device = file_session.device_list["climate"][0]
        updated = await file_session.heating.get_climate(device)
        assert updated.status is not None
        assert "current_temperature" in updated.status
        assert "target_temperature" in updated.status
        assert "mode" in updated.status

    async def test_get_light_returns_status(self, file_session):
        """get_light populates device.status with required light fields."""
        device = file_session.device_list["light"][0]
        updated = await file_session.light.get_light(device)
        assert updated.status is not None
        assert "state" in updated.status

    async def test_device_has_hive_id(self, file_session):
        """Every device in device_list has a hive_id."""
        for entity_type, devices in file_session.device_list.items():
            for device in devices:
                assert device.hive_id, f"{entity_type} device missing hive_id"

    async def test_update_data_returns_bool(self, file_session):
        """update_data returns a bool without raising."""
        device = file_session.device_list["climate"][0]
        result = await file_session.update_data(device)
        assert isinstance(result, bool)


class TestGetScheduleNnl:
    """Unit tests for HiveHelper.get_schedule_nnl — pure schedule parsing."""

    def _make_schedule(self, _offset_minutes: int = 0) -> dict:
        """Build a minimal weekly schedule with three slots per day."""
        day_names = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )
        slots = [
            {"start": 0, "value": {"target": 17.0}},
            {"start": 420, "value": {"target": 20.0}},
            {"start": 1320, "value": {"target": 18.0}},
        ]
        return {day: list(slots) for day in day_names}

    def test_returns_now_next_later(self):
        """get_schedule_nnl returns a dict with now, next, and later keys."""
        session = object.__new__(Hive)
        helper = HiveHelper(session)
        result = helper.get_schedule_nnl(self._make_schedule())
        assert set(result.keys()) == {"now", "next", "later"}

    def test_now_has_datetime_fields(self):
        """The 'now' slot contains Start_DateTime and End_DateTime."""
        session = object.__new__(Hive)
        helper = HiveHelper(session)
        result = helper.get_schedule_nnl(self._make_schedule())
        assert "Start_DateTime" in result["now"]
        assert "End_DateTime" in result["now"]

    def test_empty_schedule_returns_empty(self):
        """An empty schedule (all days have no slots) returns an empty dict."""
        session = object.__new__(Hive)
        helper = HiveHelper(session)
        empty = {
            day: []
            for day in (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        }
        result = helper.get_schedule_nnl(empty)
        assert result == {}


EXPECTED_ATTEMPTS = 2


class TestTokenRefreshRetry:
    """Tests for the retry/backoff path in session._retry_with_backoff."""

    async def test_succeeds_on_first_attempt(self):
        """A coroutine that succeeds immediately is called exactly once."""
        async with Hive(
            username="test@example.com",
            password="pass",  # pragma: allowlist secret
        ) as hive:
            calls = 0

            async def coro():
                nonlocal calls
                calls += 1
                return "ok"

            result = await hive._retry_with_backoff(coro)  # pylint: disable=protected-access
        assert result == "ok"
        assert calls == 1

    async def test_retries_on_failure_then_succeeds(self):
        """A coroutine that fails once is retried and its success is returned."""
        async with Hive(
            username="test@example.com",
            password="pass",  # pragma: allowlist secret
        ) as hive:
            attempts = []

            async def coro():
                attempts.append(1)
                if len(attempts) < EXPECTED_ATTEMPTS:
                    raise Exception("transient")  # pylint: disable=broad-exception-raised
                return "recovered"

            with patch("asyncio.sleep", new=AsyncMock()):
                result = await hive._retry_with_backoff(coro, delays=(0, 0, 0))  # pylint: disable=protected-access

        assert result == "recovered"
        assert len(attempts) == EXPECTED_ATTEMPTS

    async def test_raises_after_all_retries_exhausted(self):
        """A coroutine that always fails raises after all retries are exhausted."""
        async with Hive(
            username="test@example.com",
            password="pass",  # pragma: allowlist secret
        ) as hive:

            async def always_fails():
                raise Exception("permanent failure")  # pylint: disable=broad-exception-raised

            with patch("asyncio.sleep", new=AsyncMock()):
                with pytest.raises(Exception) as exc_info:
                    await hive._retry_with_backoff(always_fails, delays=(0, 0))  # pylint: disable=protected-access
        # The original exception instance propagates unchanged.
        assert "permanent failure" in str(exc_info.value)
