"""E2E integration tests using the bundled data.json fixture (use@file.com)."""

# pylint: disable=redefined-outer-name
import pytest


class TestGetDeviceStatus:
    """Tests that device get_* methods return populated status dicts."""

    async def test_get_climate_returns_all_fields(self, file_session):
        """Climate status has current_temperature, target_temperature, mode, boost."""
        device = file_session.device_list["climate"][0]
        updated = await file_session.heating.get_climate(device)
        assert updated.status is not None
        for field in ("current_temperature", "target_temperature", "mode", "boost"):
            assert field in updated.status

    async def test_get_light_returns_state_and_brightness(self, file_session):
        """Light status has state and brightness keys."""
        device = file_session.device_list["light"][0]
        updated = await file_session.light.get_light(device)
        assert updated.status is not None
        assert "state" in updated.status
        assert "brightness" in updated.status

    async def test_get_water_heater_returns_current_operation(self, file_session):
        """Hot-water status has current_operation key."""
        device = file_session.device_list["water_heater"][0]
        updated = await file_session.hotwater.get_water_heater(device)
        assert updated.status is not None
        assert "current_operation" in updated.status

    async def test_get_switch_returns_state(self, file_session):
        """Switch status has state key."""
        device = file_session.device_list["switch"][0]
        updated = await file_session.switch.get_switch(device)
        assert updated.status is not None
        assert "state" in updated.status

    async def test_get_sensor_returns_state(self, file_session):
        """Contact/motion sensor status has state key."""
        devices = file_session.device_list.get("binary_sensor", [])
        sensor_devices = [
            d for d in devices if d.hive_type in ("contactsensor", "motionsensor")
        ]
        if not sensor_devices:
            pytest.skip("No contact/motion sensor in fixture")
        updated = await file_session.sensor.get_sensor(sensor_devices[0])
        assert updated.status is not None
        assert "state" in updated.status

    async def test_get_action_returns_state(self, file_session):
        """Action status has state key and is not REMOVE."""
        switch_devices = file_session.device_list.get("switch", [])
        action_devices = [d for d in switch_devices if d.hive_type == "action"]
        if not action_devices:
            pytest.skip("No action in fixture")
        updated = await file_session.action.get_action(action_devices[0])
        assert updated != "REMOVE"
        assert "state" in updated.status


class TestRateLimitingAndCaching:
    """Tests for polling rate-limit and entity cache behaviour."""

    async def test_update_data_rate_limited_within_scan_interval(self, file_session):
        """Second update_data call within scan interval returns False (no re-poll)."""
        device = file_session.device_list["climate"][0]
        await file_session.heating.get_climate(device)
        result = await file_session.update_data(device)
        assert result is False

    async def test_entity_cache_round_trip(self, file_session):
        """Device stored by get_climate can be retrieved from entity cache."""
        device = file_session.device_list["climate"][0]
        await file_session.heating.get_climate(device)
        cached = file_session.get_cached_device(device)
        assert cached is not None
        assert cached.hive_id == device.hive_id

    async def test_force_update_returns_true(self, file_session):
        """force_update returns True when no poll is already in progress."""
        result = await file_session.force_update()
        assert result is True

    async def test_force_update_advances_last_update(self, file_session):
        """force_update bumps config.last_update."""
        before = file_session.config.last_update
        await file_session.force_update()
        assert file_session.config.last_update >= before


class TestDeviceListIntegrity:
    """Tests that create_devices populated all expected entity types."""

    async def test_all_devices_have_ha_name(self, file_session):
        """Every device in every entity-type list has a non-empty ha_name."""
        for entity_type, devices in file_session.device_list.items():
            for device in devices:
                assert device.ha_name, (
                    f"{entity_type} device {device.hive_id} missing ha_name"
                )

    async def test_climate_devices_present(self, file_session):
        """Fixture produces at least one climate device."""
        assert file_session.device_list.get("climate")

    async def test_light_devices_present(self, file_session):
        """Fixture produces at least one light device."""
        assert file_session.device_list.get("light")

    async def test_switch_devices_present(self, file_session):
        """Fixture produces at least one switch device."""
        assert file_session.device_list.get("switch")

    async def test_water_heater_devices_present(self, file_session):
        """Fixture produces at least one water_heater device."""
        assert file_session.device_list.get("water_heater")

    async def test_binary_sensor_devices_present(self, file_session):
        """Fixture produces at least one binary_sensor device."""
        assert file_session.device_list.get("binary_sensor")


class TestScheduleAndMinMax:
    """Tests for schedule and min/max temperature helpers."""

    async def test_climate_schedule_now_next_later(self, file_session):
        """SCHEDULE-mode climate device returns now/next/later keys."""
        climate_devices = file_session.device_list["climate"]
        schedule_devices = []
        for d in climate_devices:
            await file_session.heating.get_climate(d)
            if d.status and d.status.get("mode") == "SCHEDULE":
                schedule_devices.append(d)
        if not schedule_devices:
            pytest.skip("No climate device in SCHEDULE mode in fixture")
        result = await file_session.heating.get_schedule_now_next_later(
            schedule_devices[0]
        )
        assert result is not None
        assert set(result.keys()) >= {"now", "next", "later"}

    async def test_hotwater_schedule_now_next_later(self, file_session):
        """SCHEDULE-mode hot-water device returns schedule structure."""
        hw_devices = file_session.device_list["water_heater"]
        for d in hw_devices:
            await file_session.hotwater.get_water_heater(d)
        schedule_devices = [
            d
            for d in hw_devices
            if d.status and d.status.get("current_operation") == "SCHEDULE"
        ]
        if not schedule_devices:
            pytest.skip("No hot water device in SCHEDULE mode in fixture")
        result = await file_session.hotwater.get_schedule_now_next_later(
            schedule_devices[0]
        )
        assert result is not None

    async def test_minmax_populated_after_get_climate(self, file_session):
        """minmax_temperature returns TodayMin and TodayMax after get_climate."""
        device = file_session.device_list["climate"][0]
        await file_session.heating.get_climate(device)
        result = await file_session.heating.minmax_temperature(device)
        assert result is not None
        assert "TodayMin" in result
        assert "TodayMax" in result
