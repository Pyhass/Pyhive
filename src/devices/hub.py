"""Hive Hub Module."""

import logging
from datetime import datetime
from typing import Any

from ..helper.const import HIVETOHA, HTTP_OK
from ..helper.device_handler_base import BaseDeviceHandler
from ..helper.hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)


class HiveHub(BaseDeviceHandler):
    """Hive hub.

    Returns:
        object: Returns a hub object.
    """

    hub_type = "Hub"
    log_type = "Sensor"

    def __init__(self, session: Any = None):
        """Initialise hub.

        Args:
            session (object, optional): session to interact with Hive account. Defaults to None.
        """
        self.session = session

    async def get_smoke_status(self, device: Device):
        """Get the hub smoke status.

        Args:
            device (dict): device to get status for

        Returns:
            str: Return smoke status.
        """
        _LOGGER.debug("get_smoke_status - Getting smoke status for %s", device.hive_id)
        state = self._get_product_state(
            device, "props", "sensors", "SMOKE_CO", "active"
        )
        if state is None:
            _LOGGER.debug(
                "get_smoke_status - No smoke state found for %s", device.hive_id
            )
            return None
        result = HIVETOHA[self.hub_type]["Smoke"].get(state, state)
        _LOGGER.debug("get_smoke_status - %s smoke status: %s", device.hive_id, result)
        return result

    async def get_dog_bark_status(self, device: Device):
        """Get dog bark status.

        Args:
            device (dict): Device to get status for.

        Returns:
            str: Return status.
        """
        _LOGGER.debug(
            "get_dog_bark_status - Getting dog bark status for %s", device.hive_id
        )
        state = self._get_product_state(
            device, "props", "sensors", "DOG_BARK", "active"
        )
        if state is None:
            _LOGGER.debug(
                "get_dog_bark_status - No dog bark state found for %s", device.hive_id
            )
            return None
        result = HIVETOHA[self.hub_type]["Dog"].get(state, state)
        _LOGGER.debug(
            "get_dog_bark_status - %s dog bark status: %s", device.hive_id, result
        )
        return result

    async def get_glass_break_status(self, device: Device):
        """Get the glass detected status from the Hive hub.

        Args:
            device (dict): Device to get status for.

        Returns:
            str: Return status.
        """
        _LOGGER.debug(
            "get_glass_break_status - Getting glass break status for %s", device.hive_id
        )
        state = self._get_product_state(
            device, "props", "sensors", "GLASS_BREAK", "active"
        )
        if state is None:
            _LOGGER.debug(
                "get_glass_break_status - No glass break state found for %s",
                device.hive_id,
            )
            return None
        result = HIVETOHA[self.hub_type]["Glass"].get(state, state)
        _LOGGER.debug(
            "get_glass_break_status - %s glass break status: %s", device.hive_id, result
        )
        return result

    async def get_holiday_mode(self) -> dict | None:
        """Get the current holiday mode configuration.

        Returns:
            dict: Keys are active (bool), enabled (bool), start (epoch ms),
                end (epoch ms) and temperature. None on failure.
        """
        await self.session.hive_refresh_tokens()
        resp = await self.session.api.get_holiday_mode()
        if resp["original"] == HTTP_OK:
            return resp["parsed"]
        _LOGGER.error(
            "get_holiday_mode - Failed to fetch holiday mode: HTTP %s",
            resp["original"],
        )
        return None

    async def set_holiday_mode(
        self, start: datetime, end: datetime, temperature: float
    ) -> bool:
        """Schedule holiday mode.

        Args:
            start: Start date/time. Naive datetimes are treated as local time.
            end: End date/time. Naive datetimes are treated as local time.
            temperature: Frost-protection temperature to hold during holiday mode.

        Returns:
            bool: True if successful.
        """
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        _LOGGER.debug(
            "set_holiday_mode - Scheduling holiday mode from %s to %s at %s°.",
            start,
            end,
            temperature,
        )
        await self.session.hive_refresh_tokens()
        resp = await self.session.api.set_holiday_mode(start_ms, end_ms, temperature)
        if resp["original"] == HTTP_OK:
            return True
        _LOGGER.error("set_holiday_mode - Failed: HTTP %s", resp["original"])
        return False

    async def cancel_holiday_mode(self) -> bool:
        """Cancel any scheduled or active holiday mode.

        Returns:
            bool: True if successful.
        """
        _LOGGER.debug("cancel_holiday_mode - Cancelling holiday mode.")
        await self.session.hive_refresh_tokens()
        resp = await self.session.api.cancel_holiday_mode()
        if resp["original"] == HTTP_OK:
            return True
        _LOGGER.error("cancel_holiday_mode - Failed: HTTP %s", resp["original"])
        return False
