"""Smoke tests confirming camelCase aliases delegate to snake_case methods."""

# pylint: disable=too-few-public-methods

from unittest.mock import AsyncMock

from apyhiveapi.helper.compat_aliases import (
    ActionCompatMixin,
    HeatingCompatMixin,
    LightCompatMixin,
    SensorCompatMixin,
    SessionCompatMixin,
    SwitchCompatMixin,
    WaterHeaterCompatMixin,
)
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig


def _make_device():
    return Device(
        hive_id="h1",
        hive_name="T",
        hive_type="heating",
        ha_type="climate",
        device_id="d1",
        device_name="T",
        device_data={"online": True},
    )


# ---------------------------------------------------------------------------
# HeatingCompatMixin
# ---------------------------------------------------------------------------


class TestHeatingCompatMixin:
    """CamelCase alias smoke tests for HeatingCompatMixin."""

    async def test_set_mode_delegates(self):
        """setMode delegates to set_mode with the same arguments."""

        class Stub(HeatingCompatMixin):
            """Stub with mocked set_mode."""

            set_mode = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setMode(d, "MANUAL")
        s.set_mode.assert_called_once_with(d, "MANUAL")

    async def test_set_target_temperature_delegates(self):
        """setTargetTemperature delegates to set_target_temperature."""

        class Stub(HeatingCompatMixin):
            """Stub with mocked set_target_temperature."""

            set_target_temperature = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setTargetTemperature(d, 21.0)
        s.set_target_temperature.assert_called_once_with(d, 21.0)

    async def test_get_climate_delegates(self):
        """getClimate delegates to get_climate."""

        class Stub(HeatingCompatMixin):
            """Stub with mocked get_climate."""

            get_climate = AsyncMock(return_value=_make_device())

        s = Stub()
        d = _make_device()
        await s.getClimate(d)
        s.get_climate.assert_called_once_with(d)

    async def test_set_boost_on_delegates(self):
        """setBoostOn delegates to set_boost_on with mins and temp."""

        class Stub(HeatingCompatMixin):
            """Stub with mocked set_boost_on."""

            set_boost_on = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setBoostOn(d, 30, 22.0)
        s.set_boost_on.assert_called_once_with(d, 30, 22.0)

    async def test_set_boost_off_delegates(self):
        """setBoostOff delegates to set_boost_off."""

        class Stub(HeatingCompatMixin):
            """Stub with mocked set_boost_off."""

            set_boost_off = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setBoostOff(d)
        s.set_boost_off.assert_called_once_with(d)


# ---------------------------------------------------------------------------
# LightCompatMixin
# ---------------------------------------------------------------------------


class TestLightCompatMixin:
    """CamelCase alias smoke tests for LightCompatMixin."""

    async def test_turn_on_delegates(self):
        """turnOn delegates to turn_on with all positional args."""

        class Stub(LightCompatMixin):
            """Stub with mocked turn_on."""

            turn_on = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.turnOn(d, None, None, None)
        s.turn_on.assert_called_once_with(d, None, None, None)

    async def test_turn_off_delegates(self):
        """turnOff delegates to turn_off."""

        class Stub(LightCompatMixin):
            """Stub with mocked turn_off."""

            turn_off = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.turnOff(d)
        s.turn_off.assert_called_once_with(d)

    async def test_get_light_delegates(self):
        """getLight delegates to get_light."""

        class Stub(LightCompatMixin):
            """Stub with mocked get_light."""

            get_light = AsyncMock(return_value={})

        s = Stub()
        d = _make_device()
        await s.getLight(d)
        s.get_light.assert_called_once_with(d)


# ---------------------------------------------------------------------------
# SwitchCompatMixin
# ---------------------------------------------------------------------------


class TestSwitchCompatMixin:
    """CamelCase alias smoke tests for SwitchCompatMixin."""

    async def test_turn_on_delegates(self):
        """turnOn delegates to turn_on."""

        class Stub(SwitchCompatMixin):
            """Stub with mocked turn_on."""

            turn_on = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.turnOn(d)
        s.turn_on.assert_called_once_with(d)

    async def test_turn_off_delegates(self):
        """turnOff delegates to turn_off."""

        class Stub(SwitchCompatMixin):
            """Stub with mocked turn_off."""

            turn_off = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.turnOff(d)
        s.turn_off.assert_called_once_with(d)

    async def test_get_switch_delegates(self):
        """getSwitch delegates to get_switch."""

        class Stub(SwitchCompatMixin):
            """Stub with mocked get_switch."""

            get_switch = AsyncMock(return_value={})

        s = Stub()
        d = _make_device()
        await s.getSwitch(d)
        s.get_switch.assert_called_once_with(d)


# ---------------------------------------------------------------------------
# WaterHeaterCompatMixin
# ---------------------------------------------------------------------------


class TestWaterHeaterCompatMixin:
    """CamelCase alias smoke tests for WaterHeaterCompatMixin."""

    async def test_get_boost_delegates_to_get_boost_status(self):
        """get_boost delegates to get_boost_status and returns its result."""

        class Stub(WaterHeaterCompatMixin):
            """Stub with mocked get_boost_status."""

            get_boost_status = AsyncMock(return_value="OFF")

        s = Stub()
        d = _make_device()
        result = await s.get_boost(d)
        s.get_boost_status.assert_called_once_with(d)
        assert result == "OFF"

    async def test_set_mode_delegates(self):
        """setMode delegates to set_mode."""

        class Stub(WaterHeaterCompatMixin):
            """Stub with mocked set_mode."""

            set_mode = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setMode(d, "SCHEDULE")
        s.set_mode.assert_called_once_with(d, "SCHEDULE")

    async def test_set_boost_on_delegates(self):
        """setBoostOn delegates to set_boost_on."""

        class Stub(WaterHeaterCompatMixin):
            """Stub with mocked set_boost_on."""

            set_boost_on = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setBoostOn(d, 30)
        s.set_boost_on.assert_called_once_with(d, 30)

    async def test_set_boost_off_delegates(self):
        """setBoostOff delegates to set_boost_off."""

        class Stub(WaterHeaterCompatMixin):
            """Stub with mocked set_boost_off."""

            set_boost_off = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.setBoostOff(d)
        s.set_boost_off.assert_called_once_with(d)

    async def test_get_water_heater_delegates(self):
        """getWaterHeater delegates to get_water_heater."""

        class Stub(WaterHeaterCompatMixin):
            """Stub with mocked get_water_heater."""

            get_water_heater = AsyncMock(return_value={})

        s = Stub()
        d = _make_device()
        await s.getWaterHeater(d)
        s.get_water_heater.assert_called_once_with(d)


# ---------------------------------------------------------------------------
# SessionCompatMixin
# ---------------------------------------------------------------------------


class TestSessionCompatMixin:
    """Alias smoke tests for SessionCompatMixin."""

    async def test_start_session_delegates(self):
        """startSession delegates to start_session."""

        class Stub(SessionCompatMixin):
            """Stub with mocked start_session."""

            device_list = {}
            start_session = AsyncMock(return_value={})

        s = Stub()
        await s.startSession({})
        s.start_session.assert_called_once_with({})

    async def test_update_data_delegates(self):
        """updateData delegates to update_data."""

        class Stub(SessionCompatMixin):
            """Stub with mocked update_data."""

            device_list = {}
            update_data = AsyncMock(return_value=True)

        s = Stub()
        d = _make_device()
        await s.updateData(d)
        s.update_data.assert_called_once_with(d)

    def test_device_list_property(self):
        """deviceList property returns the same object as device_list."""

        class Stub(SessionCompatMixin):
            """Stub with a concrete device_list."""

            device_list = {"climate": []}

        s = Stub()
        assert s.deviceList == {"climate": []}
        assert s.deviceList is s.device_list

    async def test_update_interval_returns_true(self):
        """updateInterval returns True and updates config.scan_interval."""

        class Stub(SessionCompatMixin):
            """Stub for updateInterval test."""

            device_list = {}

            def __init__(self):
                self.config = SessionConfig()

        s = Stub()
        result = await s.updateInterval(60)
        assert result is True


# ---------------------------------------------------------------------------
# SessionCompatMixin.updateInterval — bug fix tests
# ---------------------------------------------------------------------------


def _make_concrete_session():
    """Return a minimal SessionCompatMixin subclass with a real SessionConfig."""

    class ConcreteSession(SessionCompatMixin):
        """Minimal concrete SessionCompatMixin for updateInterval tests."""

        def __init__(self):
            self.config = SessionConfig()
            self.device_list = {}

        async def start_session(self, config=None):  # pylint: disable=unused-argument
            """Stub."""

        async def update_data(self, device):  # pylint: disable=unused-argument
            """Stub."""

    return ConcreteSession()


class TestSessionCompatMixinUpdateInterval:
    """updateInterval must actually update config.scan_interval."""

    async def test_update_interval_sets_scan_interval(self):
        """updateInterval(300) must set self.config.scan_interval to timedelta(seconds=300)."""
        from datetime import timedelta

        session = _make_concrete_session()
        await session.updateInterval(300)
        assert session.config.scan_interval == timedelta(seconds=300)

    async def test_update_interval_returns_true(self):
        """updateInterval must return True on success."""
        session = _make_concrete_session()
        result = await session.updateInterval(60)
        assert result is True


# ---------------------------------------------------------------------------
# Migrated from test_compat_aliases_extended.py
# ---------------------------------------------------------------------------


def _make_action_device(hive_type="action", ha_type="switch"):
    return Device(
        hive_id="h1",
        hive_name="Test",
        hive_type=hive_type,
        ha_type=ha_type,
        device_id="d1",
        device_name="Test",
        device_data={},
    )


class TestSensorCompatMixin:
    """CamelCase alias smoke tests for SensorCompatMixin."""

    async def test_get_sensor_delegates(self):
        """getSensor delegates to get_sensor and returns its result."""

        class Stub(SensorCompatMixin):
            """Stub with mocked get_sensor."""

            get_sensor = AsyncMock(return_value="sensor_result")

        s = Stub()
        d = _make_action_device(hive_type="motionsensor", ha_type="binary_sensor")
        result = await s.getSensor(d)
        s.get_sensor.assert_called_once_with(d)
        assert result == "sensor_result"


class TestActionCompatMixin:
    """CamelCase alias smoke tests for ActionCompatMixin."""

    async def test_get_action_delegates(self):
        """getAction delegates to get_action and returns its result."""

        class Stub(ActionCompatMixin):
            """Stub with mocked get_action."""

            get_action = AsyncMock(return_value="action_result")

        s = Stub()
        d = _make_action_device()
        result = await s.getAction(d)
        s.get_action.assert_called_once_with(d)
        assert result == "action_result"

    async def test_set_status_on_delegates(self):
        """setStatusOn delegates to set_status_on and returns its result."""

        class Stub(ActionCompatMixin):
            """Stub with mocked set_status_on."""

            set_status_on = AsyncMock(return_value=True)

        s = Stub()
        d = _make_action_device()
        result = await s.setStatusOn(d)
        s.set_status_on.assert_called_once_with(d)
        assert result is True

    async def test_set_status_off_delegates(self):
        """setStatusOff delegates to set_status_off and returns its result."""

        class Stub(ActionCompatMixin):
            """Stub with mocked set_status_off."""

            set_status_off = AsyncMock(return_value=True)

        s = Stub()
        d = _make_action_device()
        result = await s.setStatusOff(d)
        s.set_status_off.assert_called_once_with(d)
        assert result is True
