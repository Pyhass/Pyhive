"""Hive Hub Module."""

# pylint: skip-file
import logging
from datetime import datetime

from .helper.const import HIVETOHA, HTTP_OK

_LOGGER = logging.getLogger(__name__)


class HiveHub:
    """Hive hub.

    Returns:
        object: Returns a hub object.
    """

    hubType = "Hub"
    logType = "Sensor"

    def __init__(self, session: object = None):
        """Initialise hub.

        Args:
            session (object, optional): session to interact with Hive account. Defaults to None.
        """
        self.session = session

    async def getSmokeStatus(self, device: dict):
        """Get the hub smoke status.

        Args:
            device (dict): device to get status for

        Returns:
            str: Return smoke status.
        """
        state = None
        final = None

        try:
            data = self.session.data.products[device["hiveID"]]
            state = data["props"]["sensors"]["SMOKE_CO"]["active"]
            final = HIVETOHA[self.hubType]["Smoke"].get(state, state)
        except KeyError as e:
            _LOGGER.error(e)

        return final

    async def getDogBarkStatus(self, device: dict):
        """Get dog bark status.

        Args:
            device (dict): Device to get status for.

        Returns:
            str: Return status.
        """
        state = None
        final = None

        try:
            data = self.session.data.products[device["hiveID"]]
            state = data["props"]["sensors"]["DOG_BARK"]["active"]
            final = HIVETOHA[self.hubType]["Dog"].get(state, state)
        except KeyError as e:
            _LOGGER.error(e)

        return final

    async def getGlassBreakStatus(self, device: dict):
        """Get the glass detected status from the Hive hub.

        Args:
            device (dict): Device to get status for.

        Returns:
            str: Return status.
        """
        state = None
        final = None

        try:
            data = self.session.data.products[device["hiveID"]]
            state = data["props"]["sensors"]["GLASS_BREAK"]["active"]
            final = HIVETOHA[self.hubType]["Glass"].get(state, state)
        except KeyError as e:
            _LOGGER.error(e)

        return final

    async def get_holiday_mode(self):
        """Get the current holiday mode configuration.

        Returns:
            dict: Keys are active (bool), enabled (bool), start (epoch ms),
                end (epoch ms) and temperature. None on failure.
        """
        await self.session.hiveRefreshTokens()
        resp = await self.session.api.get_holiday_mode()
        if resp.get("original") == HTTP_OK:
            return resp["parsed"]
        _LOGGER.error(
            "get_holiday_mode - Failed to fetch holiday mode: HTTP %s",
            resp.get("original"),
        )
        return None

    async def set_holiday_mode(self, start: datetime, end: datetime, temperature):
        """Schedule holiday mode.

        Args:
            start (datetime): Start date/time. Naive datetimes are local time.
            end (datetime): End date/time. Naive datetimes are local time.
            temperature (float): Frost-protection temperature to hold.

        Returns:
            boolean: True/False if successful.
        """
        start_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        _LOGGER.debug(
            "set_holiday_mode - Scheduling holiday mode from %s to %s at %s°.",
            start,
            end,
            temperature,
        )
        await self.session.hiveRefreshTokens()
        resp = await self.session.api.set_holiday_mode(start_ms, end_ms, temperature)
        if resp.get("original") == HTTP_OK:
            return True
        _LOGGER.error("set_holiday_mode - Failed: HTTP %s", resp.get("original"))
        return False

    async def cancel_holiday_mode(self):
        """Cancel any scheduled or active holiday mode.

        Returns:
            boolean: True/False if successful.
        """
        _LOGGER.debug("cancel_holiday_mode - Cancelling holiday mode.")
        await self.session.hiveRefreshTokens()
        resp = await self.session.api.cancel_holiday_mode()
        if resp.get("original") == HTTP_OK:
            return True
        _LOGGER.error("cancel_holiday_mode - Failed: HTTP %s", resp.get("original"))
        return False
