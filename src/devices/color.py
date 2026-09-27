"""Light colour sub-domain: read and set colour/temperature state."""

from __future__ import annotations

import logging
from typing import Any

from ..helper.hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)


class LightColorHandler:  # pylint: disable=no-member
    """Colour and colour-temperature methods for Hive lights.

    Expects ``self.session`` and ``self._execute_state_change`` to be
    available via the owning class's inheritance chain.
    """

    session: Any

    async def get_min_color_temp(self, device: Device):
        """Get light minimum color temperature (mireds).

        Args:
            device (Device): Device to query.

        Returns:
            int | None: Minimum colour temperature in mireds.
        """
        try:
            data = self.session.data.products[device.hive_id]
            state = data["props"]["colourTemperature"]["max"]
            return round((1 / state) * 1000000)
        except (KeyError, ZeroDivisionError) as e:
            _LOGGER.error(e)
        return None

    async def get_max_color_temp(self, device: Device):
        """Get light maximum color temperature (mireds).

        Args:
            device (Device): Device to query.

        Returns:
            int | None: Maximum colour temperature in mireds.
        """
        try:
            data = self.session.data.products[device.hive_id]
            state = data["props"]["colourTemperature"]["min"]
            return round((1 / state) * 1000000)
        except (KeyError, ZeroDivisionError) as e:
            _LOGGER.error(e)
        return None

    async def get_color_temp(self, device: Device):
        """Get light current color temperature (mireds).

        Args:
            device (Device): Device to query.

        Returns:
            int | None: Current colour temperature in mireds.
        """
        try:
            data = self.session.data.products[device.hive_id]
            state = data["state"]["colourTemperature"]
            return round((1 / state) * 1000000)
        except (KeyError, ZeroDivisionError) as e:
            _LOGGER.error(e)
        return None

    async def get_color(self, device: Device):
        """Get light current colour as an HS tuple for HA hs_color.

        Args:
            device (Device): Device to query.

        Returns:
            tuple | None: ``(hue_degrees, saturation_percent)`` where hue is
                0–360 and saturation is 0–100, or None on error.
        """
        try:
            data = self.session.data.products[device.hive_id]
            return (data["state"]["hue"], data["state"]["saturation"])
        except KeyError as e:
            _LOGGER.error(e)
        return None

    async def get_color_mode(self, device: Device):
        """Get colour mode (``"COLOUR"`` or ``"WHITE"``).

        Args:
            device (Device): Device to query.

        Returns:
            str | None: Current colour mode.
        """
        try:
            data = self.session.data.products[device.hive_id]
            return data["state"]["colourMode"]
        except KeyError as e:
            _LOGGER.error(e)
        return None

    async def set_color_temp(self, device: Device, color_temp: int):
        """Set colour temperature of the light.

        Args:
            device (Device): Device to update.
            color_temp (int): Colour temperature in mireds.

        Returns:
            bool: True on success.
        """
        _LOGGER.debug(
            "set_color_temp - Setting colour temperature to %s for %s.",
            color_temp,
            device.ha_name,
        )
        # Non-tuneable lights also need colourMode set to WHITE
        data = self.session.data.products.get(device.hive_id, {})
        kwargs: dict[str, Any] = {"colourTemperature": color_temp}
        if data.get("type") != "tuneablelight":
            kwargs["colourMode"] = "WHITE"
        return await self._execute_state_change(device, **kwargs)  # type: ignore[attr-defined]

    async def set_color(self, device: Device, new_color: list):
        """Set colour of the light (HSV).

        Args:
            device (Device): Device to update.
            new_color (list): ``[hue, saturation, value]`` as integers.

        Returns:
            bool: True on success.
        """
        _LOGGER.debug(
            "set_color - Setting colour to %s for %s.", new_color, device.ha_name
        )
        return await self._execute_state_change(  # type: ignore[attr-defined]
            device,
            colourMode="COLOUR",
            hue=str(new_color[0]),
            saturation=str(new_color[1]),
            value=str(new_color[2]),
        )
