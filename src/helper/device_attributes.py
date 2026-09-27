"""Hive Device Attribute Module."""

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)


class HiveAttributes:
    """Device Attributes Code."""

    def __init__(self, session: Any = None):
        """Initialise attributes.

        Args:
            session (object, optional): Session to interact with hive account. Defaults to None.
        """
        self.session = session

    async def state_attributes(self, n_id: str, _type: str):
        """Get HA State Attributes.

        Args:
            n_id (str): The id of the device.
            _type (str): The device type.

        Returns:
            dict: Set of attributes.
        """
        attr = {}

        if n_id in self.session.data.products or n_id in self.session.data.devices:
            attr.update({"available": (await self.online_offline(n_id))})
            if n_id in self.session.config.battery:
                battery = await self.get_battery(n_id)
                if battery is not None:
                    attr.update({"battery": str(battery) + "%"})
            if n_id in self.session.config.mode:
                attr.update({"mode": (await self.get_mode(n_id))})
        return attr

    async def online_offline(self, n_id: str):
        """Check if device is online.

        Args:
            n_id (str): The id of the device.

        Returns:
            boolean: True/False if device online.
        """
        state = None

        try:
            data = self.session.data.devices[n_id]
            state = data["props"]["online"]
        except KeyError as e:
            _LOGGER.error(e)

        return state

    async def get_mode(self, n_id: str):
        """Get sensor mode.

        Args:
            n_id (str): The id of the device

        Returns:
            str: The mode of the device.
        """
        try:
            data = self.session.data.products[n_id]
            return data["state"]["mode"]
        except KeyError as e:
            _LOGGER.error(e)
        return None

    async def get_battery(self, n_id: str):
        """Get device battery level.

        Args:
            n_id (str): The id of the device.

        Returns:
            str: Battery level of device.
        """
        state = None
        final = None

        try:
            data = self.session.data.devices[n_id]
            state = data["props"]["battery"]
            final = state
        except KeyError as e:
            _LOGGER.error(e)

        return final
