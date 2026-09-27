"""Hive Light Module."""

import logging
from typing import Any

from ..helper.compat_aliases import LightCompatMixin
from ..helper.const import HIVETOHA
from ..helper.device_handler_base import BaseDeviceHandler
from ..helper.hivedataclasses import Device
from .color import LightColorHandler

_LOGGER = logging.getLogger(__name__)


class HiveLight(LightColorHandler, BaseDeviceHandler):
    """Hive Light Code.

    Returns:
        object: Hivelight
    """

    session: Any
    light_type = "Light"

    async def get_state(self, device: Device):
        """Get light current state.

        Args:
            device (dict): Device to get the state of.

        Returns:
            str: State of the light.
        """
        state = None
        final = None
        device_name = device.ha_name

        try:
            data = self.session.data.products[device.hive_id]
            state = data["state"]["status"]
            final = HIVETOHA[self.light_type].get(state, state)
        except KeyError as e:
            _LOGGER.error(
                "KeyError getting light state for %s: %s", device_name, str(e)
            )

        return final

    async def get_brightness(self, device: Device):
        """Get light current brightness.

        Args:
            device (dict): Device to get the brightness of.

        Returns:
            int: Brightness value.
        """
        state = None
        final = None
        device_name = device.ha_name

        try:
            data = self.session.data.products[device.hive_id]
            state = data["state"]["brightness"]
            final = int((state / 100) * 255)
        except (KeyError, TypeError) as e:
            _LOGGER.error(
                "Error getting light brightness for %s: %s", device_name, str(e)
            )

        return final

    async def set_status_off(self, device: Device):
        """Set light to turn off.

        Args:
            device (dict): Device to turn off.

        Returns:
            boolean: True/False if successful
        """
        _LOGGER.info("Turning off light %s", device.ha_name)
        return await self._execute_state_change(device, status="OFF")

    async def set_status_on(self, device: Device):
        """Set light to turn on.

        Args:
            device (dict): Device to turn on.

        Returns:
            boolean: True/False if successful
        """
        _LOGGER.info("Turning on light %s", device.ha_name)
        return await self._execute_state_change(device, status="ON")

    async def set_brightness(self, device: Device, n_brightness: int):
        """Set brightness of the light.

        Args:
            device (dict): Device to set brightness of.
            n_brightness (int): Brightness value to set the light to.

        Returns:
            boolean: True/False if successful
        """
        _LOGGER.info(
            "Setting brightness to %s for light %s", n_brightness, device.ha_name
        )
        return await self._execute_state_change(
            device, status="ON", brightness=n_brightness
        )


class Light(LightCompatMixin, HiveLight):
    """Home Assistant Light Code.

    Args:
        HiveLight (object): HiveLight Code.
    """

    def __init__(self, session: Any = None):
        """Initialise light.

        Args:
            session (object, optional): Used to interact with the hive account. Defaults to None.
        """
        self.session = session

    async def get_light(self, device: Device):
        """Get light data.

        Args:
            device (dict): Device to update.

        Returns:
            dict: Updated device.
        """
        if self.session.should_use_cached_data():
            cached = self.session.get_cached_device(device)
            if cached is not None:
                _LOGGER.debug(
                    "get_light - Returning cached state for light %s (slow/busy poll).",
                    device.ha_name,
                )
                return cached
        online = await self.session.attr.online_offline(device.device_id)
        if not isinstance(device.device_data, dict):
            device.device_data = {}
        device.device_data["online"] = online

        if device.device_data["online"]:
            self.session.helper.device_recovered(device.device_id)
            _LOGGER.debug("get_light - Updating light data for %s.", device.ha_name)
            data = self.session.data.devices[device.device_id]
            device.status = {
                "state": await self.get_state(device),
                "brightness": await self.get_brightness(device),
            }
            props = data.get("props") or {}
            props["online"] = online
            device.device_data = props
            device.parent_device = data.get("parent", None)
            device.attributes = await self.session.attr.state_attributes(
                device.device_id, device.hive_type
            )

            if device.hive_type in ("tuneablelight", "colourtuneablelight"):
                device.status["color_temp"] = await self.get_color_temp(device)
            if device.hive_type == "colourtuneablelight":
                mode = await self.get_color_mode(device)
                device.status["mode"] = mode
                if mode == "COLOUR":
                    device.status["hs_color"] = await self.get_color(device)

            _LOGGER.debug(
                "get_light - Light device data for %s: %s",
                device.ha_name,
                device.status,
            )

            return self.session.set_cached_device(device)
        await self.session.helper.error_check(
            device.device_id, "ERROR", device.device_data["online"]
        )
        device.status = device.status or {"state": None}
        return device

    async def turn_on(
        self,
        device: Device,
        brightness: int | None,
        color_temp: int | None,
        color: list | None,
    ):
        """Set light to turn on.

        Args:
            device (dict): Device to turn on
            brightness (int): Brightness value to set the light to.
            color_temp (int): Color Temp value to set the light to.
            color (list): colour values to set the light to.

        Returns:
            boolean: True/False if successful.
        """
        if brightness is not None:
            return await self.set_brightness(device, brightness)
        if color_temp is not None:
            return await self.set_color_temp(device, color_temp)
        if color is not None:
            return await self.set_color(device, color)

        return await self.set_status_on(device)

    async def turn_off(self, device: Device):
        """Set light to turn off.

        Args:
            device (dict): Device to be turned off.

        Returns:
            boolean: True/False if successful.
        """
        return await self.set_status_off(device)
