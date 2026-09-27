"""Hive Sensor Module."""

import logging
from typing import Any

from ..helper.compat_aliases import SensorCompatMixin
from ..helper.const import HIVE_TYPES, HIVETOHA
from ..helper.device_handler_base import BaseDeviceHandler
from ..helper.hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)

sensor_commands = {
    "SMOKE_CO": lambda s, d: s.session.hub.get_smoke_status(d),
    "DOG_BARK": lambda s, d: s.session.hub.get_dog_bark_status(d),
    "GLASS_BREAK": lambda s, d: s.session.hub.get_glass_break_status(d),
    "Current_Temperature": lambda s, d: s.session.heating.get_current_temperature(d),
    "Heating_Current_Temperature": lambda s, d: (
        s.session.heating.get_current_temperature(d)
    ),
    "Heating_Target_Temperature": lambda s, d: s.session.heating.get_target_temperature(
        d
    ),
    "Heating_State": lambda s, d: s.session.heating.get_state(d),
    "Heating_Mode": lambda s, d: s.session.heating.get_mode(d),
    "Heating_Boost": lambda s, d: s.session.heating.get_boost_status(d),
    "Hotwater_State": lambda s, d: s.session.hotwater.get_state(d),
    "Hotwater_Mode": lambda s, d: s.session.hotwater.get_mode(d),
    "Hotwater_Boost": lambda s, d: s.session.hotwater.get_boost(d),
    "Battery": lambda s, d: s.session.attr.get_battery(d.device_id),
    "Mode": lambda s, d: s.session.attr.get_mode(d.hive_id),
    "Availability": lambda s, d: s.online(d),
    "Connectivity": lambda s, d: s.online(d),
    "Power": lambda s, d: s.session.switch.get_power_usage(d),
}


class HiveSensor(BaseDeviceHandler):
    """Hive Sensor Code."""

    session: Any
    sensor_type = "Sensor"

    async def get_state(self, device: Device):
        """Get sensor state.

        Args:
            device (dict): Device to get state off.

        Returns:
            str: State of device.
        """
        state = None
        final = None

        try:
            data = self.session.data.products[device.hive_id]
            if data["type"] == "contactsensor":
                state = data["props"]["status"]
                final = HIVETOHA[self.sensor_type].get(state, state)
            elif data["type"] == "motionsensor":
                final = data["props"]["motion"]["status"]
        except KeyError as e:
            _LOGGER.error(e)

        return final

    async def online(self, device: Device):
        """Get the online status of the Hive hub.

        Args:
            device (dict): Device to get the state of.

        Returns:
            boolean: True/False if the device is online.
        """
        state = None
        final = None

        try:
            data = self.session.data.devices[device.device_id]
            state = data["props"]["online"]
            final = HIVETOHA[self.sensor_type].get(state, state)
        except KeyError as e:
            _LOGGER.error(e)

        return final


class Sensor(SensorCompatMixin, HiveSensor):
    """Home Assisatnt sensor code.

    Args:
        HiveSensor (object): Hive sensor code.
    """

    def __init__(self, session: Any = None):
        """Initialise sensor.

        Args:
            session (object, optional): session to interact with Hive account. Defaults to None.
        """
        self.session = session

    async def get_sensor(self, device: Device):
        """Gets updated sensor data.

        Args:
            device (dict): Device to update.

        Returns:
            dict: Updated device.
        """
        if self.session.should_use_cached_data():
            cached = self.session.get_cached_device(device)
            if cached is not None:
                _LOGGER.debug(
                    "Returning cached state for sensor %s (slow/busy poll).",
                    device.ha_name,
                )
                return cached
        online = await self.session.attr.online_offline(device.device_id)
        if not isinstance(device.device_data, dict):
            device.device_data = {}
        device.device_data["online"] = online
        data = {}

        if device.device_data["online"] or device.hive_type in (
            "Availability",
            "Connectivity",
        ):
            if device.hive_type not in ("Availability", "Connectivity"):
                self.session.helper.device_recovered(device.device_id)

            _LOGGER.debug(
                "get_sensor - Updating sensor data for %s (%s).",
                device.ha_name,
                device.hive_type,
            )

            if device.device_id in self.session.data.devices:
                data = self.session.data.devices.get(device.device_id, {})
            elif device.hive_id in self.session.data.products:
                data = self.session.data.products.get(device.hive_id, {})

            if (
                device.hive_type in sensor_commands
                or getattr(device, "custom", None) in sensor_commands
            ):
                code = sensor_commands.get(
                    device.hive_type,
                    sensor_commands.get(getattr(device, "custom", "")),
                )
                device.status = {"state": await code(self, device)}  # type: ignore[misc]
                props = data.get("props") or {}
                props["online"] = online
                device.device_data = props
                device.parent_device = data.get("parent", None)
            elif device.hive_type in HIVE_TYPES["Sensor"]:
                data = self.session.data.devices.get(device.device_id, {})
                device.status = {"state": await self.get_state(device)}
                props = data.get("props") or {}
                props["online"] = online
                device.device_data = props
                device.parent_device = data.get("parent", None)
                device.attributes = await self.session.attr.state_attributes(
                    device.device_id, device.hive_type
                )

            _LOGGER.debug(
                "get_sensor - Sensor device data for %s: %s",
                device.ha_name,
                device.status,
            )

            return self.session.set_cached_device(device)
        await self.session.helper.error_check(
            device.device_id, "ERROR", device.device_data["online"]
        )
        device.status = device.status or {"state": None}
        return device
