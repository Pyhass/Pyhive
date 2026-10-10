"""Tests for Switch / HiveSmartPlug (src/devices/plug.py)."""

from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.plug import Switch
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

HTTP_200 = 200


def _make_switch(products=None, devices=None):
    """Build a Switch with a mocked session."""
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
    session.api.set_state = AsyncMock(return_value={"original": HTTP_200, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    session.should_use_cached_data = MagicMock(return_value=False)
    session.get_cached_device = MagicMock(return_value=None)
    session.set_cached_device = MagicMock(side_effect=lambda d: d)
    session.heating = MagicMock()
    session.heating.get_heat_on_demand = AsyncMock(return_value=True)
    session.heating.set_heat_on_demand = AsyncMock(return_value=True)
    return Switch(session=session)


def _make_device(hive_id="plug-1", device_id="dev-1", hive_type="activeplug"):
    """Return a minimal switch Device."""
    return Device(
        hive_id=hive_id,
        hive_name="Plug",
        hive_type=hive_type,
        ha_type="switch",
        device_id=device_id,
        device_name="Plug",
        device_data={"online": True},
        ha_name="Smart Plug",
    )


class TestGetState:
    """Tests for HiveSmartPlug.get_state."""

    async def test_on_returns_true(self):
        """get_state returns True when plug state is ON."""
        sw = _make_switch({"plug-1": {"state": {"status": "ON"}, "props": {}}})
        assert await sw.get_state(_make_device()) is True

    async def test_off_returns_false(self):
        """get_state returns False when plug state is OFF."""
        sw = _make_switch({"plug-1": {"state": {"status": "OFF"}, "props": {}}})
        assert await sw.get_state(_make_device()) is False


class TestGetPowerUsage:
    """Tests for HiveSmartPlug.get_power_usage."""

    async def test_returns_power_consumption(self):
        """get_power_usage returns the powerConsumption value from product props."""
        sw = _make_switch(
            {"plug-1": {"props": {"powerConsumption": 42.5}, "state": {}}}
        )
        assert await sw.get_power_usage(_make_device()) == 42.5  # noqa: PLR2004

    async def test_missing_product_returns_none(self):
        """get_power_usage returns None when the product key is absent."""
        sw = _make_switch()
        assert await sw.get_power_usage(_make_device()) is None


class TestSetStatus:
    """Tests for HiveSmartPlug.set_status_on and set_status_off."""

    async def test_set_status_on_calls_execute(self):
        """set_status_on calls _execute_state_change with status='ON' and returns True."""
        sw = _make_switch({"plug-1": {"type": "activeplug", "state": {}, "props": {}}})
        result = await sw.set_status_on(_make_device())
        assert result is True
        sw.session.api.set_state.assert_called_once()
        _, kwargs = sw.session.api.set_state.call_args
        assert kwargs.get("status") == "ON"

    async def test_set_status_off_calls_execute(self):
        """set_status_off calls _execute_state_change and returns True on success."""
        sw = _make_switch({"plug-1": {"type": "activeplug", "state": {}, "props": {}}})
        result = await sw.set_status_off(_make_device())
        assert result is True


class TestGetSwitchState:
    """Tests for Switch.get_switch_state."""

    async def test_heat_on_demand_routes_to_heating(self):
        """get_switch_state delegates to heating.get_heat_on_demand for Heat_On_Demand type."""
        sw = _make_switch()
        d = _make_device(hive_type="Heating_Heat_On_Demand")
        await sw.get_switch_state(d)
        sw.session.heating.get_heat_on_demand.assert_called_once_with(d)

    async def test_normal_type_calls_get_state(self):
        """get_switch_state calls get_state for standard activeplug hive_type."""
        sw = _make_switch({"plug-1": {"state": {"status": "ON"}, "props": {}}})
        result = await sw.get_switch_state(_make_device())
        assert result is True


class TestTurnOnOff:
    """Tests for Switch.turn_on and turn_off."""

    async def test_turn_on_heat_on_demand_calls_set_heat_on_demand_enabled(self):
        """turn_on delegates to heating.set_heat_on_demand with 'ENABLED' for Heat_On_Demand."""
        sw = _make_switch()
        d = _make_device(hive_type="Heating_Heat_On_Demand")
        await sw.turn_on(d)
        sw.session.heating.set_heat_on_demand.assert_called_once_with(d, "ENABLED")

    async def test_turn_off_heat_on_demand_calls_disabled(self):
        """turn_off delegates to heating.set_heat_on_demand with 'DISABLED' for Heat_On_Demand."""
        sw = _make_switch()
        d = _make_device(hive_type="Heating_Heat_On_Demand")
        await sw.turn_off(d)
        sw.session.heating.set_heat_on_demand.assert_called_once_with(d, "DISABLED")

    async def test_turn_on_normal_calls_set_status_on(self):
        """turn_on calls set_status_on for standard activeplug type."""
        sw = _make_switch({"plug-1": {"type": "activeplug", "state": {}, "props": {}}})
        result = await sw.turn_on(_make_device())
        assert result is True

    async def test_turn_off_normal_calls_set_status_off(self):
        """turn_off calls set_status_off for standard activeplug type."""
        sw = _make_switch({"plug-1": {"type": "activeplug", "state": {}, "props": {}}})
        result = await sw.turn_off(_make_device())
        assert result is True


class TestGetSwitch:
    """Tests for Switch.get_switch."""

    async def test_online_activeplug_has_state_and_power_usage(self):
        """get_switch populates both state and power_usage for an online activeplug."""
        products = {
            "plug-1": {
                "type": "activeplug",
                "state": {"status": "ON"},
                "props": {"powerConsumption": 10.0},
            }
        }
        devices = {"dev-1": {"props": {"online": True}}}
        sw = _make_switch(products=products, devices=devices)
        d = _make_device()
        result = await sw.get_switch(d)
        assert "state" in result.status
        assert "power_usage" in result.status

    async def test_offline_defaults_status(self):
        """get_switch sets status to {'state': None} when device is offline."""
        sw = _make_switch()
        sw.session.attr.online_offline.return_value = False
        d = _make_device()
        result = await sw.get_switch(d)
        assert result.status == {"state": None}

    async def test_cached_returns_cached(self):
        """get_switch returns the cached device when should_use_cached_data is True."""
        sw = _make_switch()
        sw.session.should_use_cached_data.return_value = True
        cached = _make_device()
        sw.session.get_cached_device.return_value = cached
        result = await sw.get_switch(_make_device())
        assert result is cached

    async def test_cached_miss_falls_through_to_live_fetch(self):
        """When cache is checked but empty, get_switch performs the live update."""
        products = {
            "plug-1": {
                "type": "activeplug",
                "state": {"status": "ON"},
                "props": {"powerConsumption": 5.0},
            }
        }
        devices = {"dev-1": {"props": {"online": True}}}
        sw = _make_switch(products=products, devices=devices)
        sw.session.should_use_cached_data.return_value = True
        sw.session.get_cached_device.return_value = None
        result = await sw.get_switch(_make_device())
        assert result.status["state"] is True
        assert "power_usage" in result.status
        sw.session.attr.online_offline.assert_awaited_once()

    async def test_non_dict_device_data_is_replaced(self):
        """If device.device_data is not a dict it is replaced with one before assigning online."""
        products = {
            "plug-1": {
                "type": "activeplug",
                "state": {"status": "OFF"},
                "props": {"powerConsumption": 0.0},
            }
        }
        devices = {"dev-1": {"props": {"online": True}}}
        sw = _make_switch(products=products, devices=devices)
        d = _make_device()
        d.device_data = None
        result = await sw.get_switch(d)
        assert isinstance(result.device_data, dict)
        assert result.device_data.get("online") is True

    async def test_non_activeplug_skips_power_usage_and_attributes(self):
        """Non-activeplug hive_type runs the online branch but skips activeplug-only fields."""
        products = {"plug-1": {"state": {"status": "ON"}, "props": {}}}
        devices = {"dev-1": {"props": {"online": True}}}
        sw = _make_switch(products=products, devices=devices)
        d = _make_device(hive_type="Heating_Heat_On_Demand")
        result = await sw.get_switch(d)
        assert "power_usage" not in result.status
        assert result.attributes == {}
        sw.session.attr.state_attributes.assert_not_called()
        sw.session.heating.get_heat_on_demand.assert_awaited_once_with(d)
