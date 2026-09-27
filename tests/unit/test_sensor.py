"""Extended branch-coverage tests for Sensor (devices/sensor.py)."""

# pylint: disable=protected-access

from unittest.mock import AsyncMock, MagicMock, patch

from apyhiveapi.devices.sensor import Sensor
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map


def _make_session(products=None, devices=None):
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
    session.api = MagicMock()
    session.api.set_state = AsyncMock(return_value={"original": 200, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    return session


def _make_device(
    hive_id="sensor-1",
    device_id="dev-1",
    hive_type="contactsensor",
    ha_type="binary_sensor",
):
    return Device(
        hive_id=hive_id,
        hive_name="Front Door",
        hive_type=hive_type,
        ha_type=ha_type,
        device_id=device_id,
        device_name="Front Door",
        device_data={"online": True},
        ha_name="Front Door",
    )


class TestGetSensor:
    """Tests for Sensor.get_sensor covering previously uncovered branches."""

    async def test_cache_hit_returns_cached(self):
        """Lines 92-97: should_use_cached_data True + cache hit returns cached device."""
        session = _make_session()
        cached_device = _make_device()
        session.should_use_cached_data = MagicMock(return_value=True)
        session.get_cached_device = MagicMock(return_value=cached_device)

        sensor = Sensor(session=session)
        device = _make_device()
        result = await sensor.get_sensor(device)

        assert result is cached_device
        session.attr.online_offline.assert_not_called()

    async def test_device_data_not_dict_gets_initialized(self):
        """Line 100: non-dict device_data is replaced with an empty dict."""
        hive_id = "sensor-1"
        device_id = "dev-1"
        products = {
            hive_id: {
                "type": "contactsensor",
                "props": {"status": "CLOSED"},
            }
        }
        devices = {device_id: {"props": {"online": True}, "parent": None}}
        session = _make_session(products=products, devices=devices)

        sensor = Sensor(session=session)
        device = _make_device(hive_id=hive_id, device_id=device_id)
        device.device_data = None  # not a dict

        result = await sensor.get_sensor(device)

        assert isinstance(result.device_data, dict)

    async def test_hive_id_in_products_when_not_in_devices(self):
        """Lines 119-120: device_id not in devices but hive_id in products → reads products."""
        hive_id = "sensor-2"
        device_id = "dev-missing"
        products = {
            hive_id: {
                "type": "contactsensor",
                "props": {"status": "OPEN"},
            }
        }
        # devices does NOT contain device_id; the elif branch should fire
        session = _make_session(products=products, devices={})

        sensor = Sensor(session=session)
        device = _make_device(
            hive_id=hive_id,
            device_id=device_id,
            hive_type="contactsensor",
        )
        # Ensure set_cached_device returns the device so we can inspect it
        session.set_cached_device = MagicMock(side_effect=lambda d: d)

        result = await sensor.get_sensor(device)

        # The HIVE_TYPES["Sensor"] branch sets device.status
        assert result.status is not None
        assert "state" in result.status

    async def test_contact_sensor_in_hive_types_sets_status(self):
        """Lines 135-144: contactsensor hits HIVE_TYPES["Sensor"] branch and status is set."""
        hive_id = "sensor-3"
        device_id = "dev-3"
        products = {
            hive_id: {
                "type": "contactsensor",
                "props": {"status": "CLOSED"},
            }
        }
        devices = {device_id: {"props": {"online": True}, "parent": None}}
        session = _make_session(products=products, devices=devices)

        sensor = Sensor(session=session)
        device = _make_device(
            hive_id=hive_id,
            device_id=device_id,
            hive_type="contactsensor",
        )
        result = await sensor.get_sensor(device)

        assert result.status is not None
        assert "state" in result.status
        session.attr.state_attributes.assert_awaited_once()

    async def test_contact_sensor_uses_device_id_not_hive_id_for_props(self):
        """HIVE_TYPES['Sensor'] branch must look up data.devices by device_id.

        Before the fix, line 160 used hive_id; data was always {} so
        device.parent_device was always None even when the device existed.
        """
        hive_id = "prod-abc"
        device_id = "dev-xyz"  # deliberately different from hive_id

        products = {}  # contactsensor is NOT in products
        devices = {
            device_id: {
                "props": {"online": True, "signal": -70},
                "parent": "hub-parent-id",
            }
        }
        session = _make_session(products=products, devices=devices)
        session.attr.online_offline = AsyncMock(return_value=True)

        device = _make_device(
            hive_id=hive_id, device_id=device_id, hive_type="contactsensor"
        )
        device.device_data = {"online": True}

        sensor = Sensor(session)
        with patch.object(sensor, "get_state", new=AsyncMock(return_value="CLOSED")):
            result = await sensor.get_sensor(device)

        assert result is not None
        assert device.parent_device == "hub-parent-id", (
            "parent_device must come from data.devices[device_id], not hive_id lookup"
        )


class TestGetState:
    """Tests for HiveSensor.get_state covering the motionsensor branch (lines 37-42)."""

    async def test_motionsensor_returns_motion_status(self):
        """Lines 37-38: data['type'] == 'motionsensor' returns motion status."""
        hive_id = "motion-1"
        products = {
            hive_id: {
                "type": "motionsensor",
                "props": {"motion": {"status": True}},
            }
        }
        session = _make_session(products=products)

        sensor = Sensor(session=session)
        device = _make_device(
            hive_id=hive_id,
            device_id="dev-motion",
            hive_type="motionsensor",
        )
        state = await sensor.get_state(device)

        assert state is True


# ===========================================================================
# Migrated from test_remaining_branches.py
# ===========================================================================


class TestSensorGetStateKeyError:
    """Lines 37->42: KeyError in HiveSensor.get_state."""

    async def test_get_state_missing_type_key_returns_none(self):
        """Product with no 'type' key causes KeyError → final stays None."""
        session = _make_session({"sens-1": {}})
        sensor = Sensor(session=session)
        d = _make_device(hive_id="sens-1", device_id="dev-1", hive_type="contactsensor")
        result = await sensor.get_state(d)
        assert result is None

    async def test_get_state_missing_props_key_returns_none(self):
        """contactsensor product without 'props' causes KeyError → None."""
        session = _make_session({"sens-1": {"type": "contactsensor"}})
        sensor = Sensor(session=session)
        d = _make_device(hive_id="sens-1", device_id="dev-1", hive_type="contactsensor")
        result = await sensor.get_state(d)
        assert result is None


class TestSensorGetStateUnknownType:
    """Lines 37->42: data['type'] is neither contactsensor nor motionsensor."""

    async def test_unknown_type_returns_none(self):
        """Product with type 'hub' skips both if/elif → final stays None."""
        session = _make_session({"sens-1": {"type": "hub", "props": {}}})
        sensor = Sensor(session=session)
        d = _make_device(hive_id="sens-1", device_id="dev-1", hive_type="contactsensor")
        result = await sensor.get_state(d)
        assert result is None


class TestSensorGetSensorCacheMiss:
    """Lines 92->98: should_use_cached_data=True but cached is None."""

    async def test_cached_none_falls_through(self):
        session = _make_session(
            products={"sens-1": {"type": "contactsensor", "props": {"status": "OPEN"}}},
            devices={"dev-1": {"props": {"online": True}, "type": "contactsensor"}},
        )
        session.should_use_cached_data.return_value = True
        session.get_cached_device.return_value = None
        sensor = Sensor(session=session)
        d = _make_device(hive_id="sens-1", device_id="dev-1", hive_type="contactsensor")
        result = await sensor.get_sensor(d)
        assert result is not None
        session.attr.online_offline.assert_called_once()


class TestSensorGetSensorNoDataFallthrough:
    """Lines 119->122: device_id not in devices AND hive_id not in products."""

    async def test_neither_match_continues_with_empty_data(self):
        """data stays empty dict when neither lookup succeeds."""
        session = _make_session(products={}, devices={})
        sensor = Sensor(session=session)
        d = _make_device(
            hive_id="unknown-hive",
            device_id="unknown-dev",
            hive_type="contactsensor",
        )
        result = await sensor.get_sensor(d)
        # Should not raise; result will be the device (set_cached_device returns it)
        assert result is not None


class TestSensorGetSensorUnknownHiveType:
    """Lines 135->146: hive_type not in sensor_commands and not in HIVE_TYPES['Sensor']."""

    async def test_hive_type_not_in_either_dict_skips_both_branches(self):
        """activeplug is neither in sensor_commands nor HIVE_TYPES['Sensor']."""
        session = _make_session(
            devices={"dev-1": {"props": {"online": True}, "type": "activeplug"}}
        )
        sensor = Sensor(session=session)
        d = _make_device(hive_id="dev-1", device_id="dev-1", hive_type="activeplug")
        d.device_data = {"online": True}
        result = await sensor.get_sensor(d)
        # Neither branch sets device.status; device returned as-is via set_cached_device
        assert result is not None
