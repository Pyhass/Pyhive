"""Tests for Sensor / HiveSensor."""

from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.sensor import Sensor
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map


def _make_sensor(products=None, devices=None):
    """Build a Sensor with a mocked session."""
    session = MagicMock()
    session.data = Map(
        {
            "products": products or {},
            "devices": devices or {},
            "actions": {},
            "minMax": {},
            "user": {},
        }
    )
    session.config = SessionConfig()
    session.helper = MagicMock()
    session.helper.device_recovered = MagicMock()
    session.helper.error_check = AsyncMock()
    session.attr = MagicMock()
    session.attr.online_offline = AsyncMock(return_value=True)
    session.attr.state_attributes = AsyncMock(return_value={})
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return Sensor(session=session)


def _make_device(hive_id="sens-1", device_id="dev-1", hive_type="contactsensor"):
    """Return a minimal binary_sensor Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Front Door",
        hive_type=hive_type,
        ha_type="binary_sensor",
        device_id=device_id,
        device_name="Front Door",
        device_data={"online": True},
        ha_name="Front Door",
    )


class TestGetState:
    """Tests for HiveSensor.get_state."""

    async def test_contactsensor_open_returns_true(self):
        """get_state returns True for a contactsensor with status OPEN."""
        sensor = _make_sensor(
            products={"sens-1": {"type": "contactsensor", "props": {"status": "OPEN"}}}
        )
        assert await sensor.get_state(_make_device()) is True

    async def test_contactsensor_closed_returns_false(self):
        """get_state returns False for a contactsensor with status CLOSED."""
        sensor = _make_sensor(
            products={
                "sens-1": {"type": "contactsensor", "props": {"status": "CLOSED"}}
            }
        )
        assert await sensor.get_state(_make_device()) is False

    async def test_missing_key_returns_none(self):
        """get_state returns None when the hive_id is not in products."""
        sensor = _make_sensor()
        assert await sensor.get_state(_make_device()) is None


class TestOnline:
    """Tests for HiveSensor.online."""

    async def test_online_returns_online_string(self):
        """online() maps True -> 'Online' via HIVETOHA['Sensor']."""
        sensor = _make_sensor(devices={"dev-1": {"props": {"online": True}}})
        assert await sensor.online(_make_device()) == "Online"

    async def test_offline_returns_offline_string(self):
        """online() maps False -> 'Offline' via HIVETOHA['Sensor']."""
        sensor = _make_sensor(devices={"dev-1": {"props": {"online": False}}})
        assert await sensor.online(_make_device()) == "Offline"

    async def test_missing_device_returns_none(self):
        """online() returns None when the device_id is not in devices."""
        sensor = _make_sensor()
        assert await sensor.online(_make_device()) is None


class TestGetSensor:
    """Tests for Sensor.get_sensor."""

    async def test_online_contact_sensor_populates_status(self):
        """get_sensor populates device.status with state for an online contactsensor."""
        sensor = _make_sensor(
            products={"sens-1": {"type": "contactsensor", "props": {"status": "OPEN"}}},
            devices={"dev-1": {"props": {"online": True}}},
        )
        d = _make_device()
        result = await sensor.get_sensor(d)
        assert result.status == {"state": True}

    async def test_offline_defaults_status(self):
        """get_sensor sets status to {'state': None} when device is offline."""
        sensor = _make_sensor()
        sensor.session.attr.online_offline.return_value = False
        d = _make_device()
        result = await sensor.get_sensor(d)
        assert result.status == {"state": None}

    async def test_cached_returns_cached(self):
        """get_sensor returns the cached device when should_use_cached_data is True."""
        sensor = _make_sensor()
        sensor.session.should_use_cached_data.return_value = True
        cached = _make_device()
        sensor.session.get_cached_device.return_value = cached
        result = await sensor.get_sensor(_make_device())
        assert result is cached

    async def test_availability_type_skips_device_recovered(self):
        """get_sensor does not call device_recovered for Availability hive_type."""
        sensor = _make_sensor(devices={"dev-1": {"props": {"online": True}}})
        d = _make_device(hive_type="Availability")
        await sensor.get_sensor(d)
        sensor.session.helper.device_recovered.assert_not_called()
