"""Start Hive Session."""

import asyncio
import logging

from aiohttp import ClientSession

from .devices.action import HiveAction
from .devices.heating import Climate
from .devices.hotwater import WaterHeater
from .devices.hub import HiveHub
from .devices.light import Light
from .devices.plug import Switch
from .devices.sensor import Sensor
from .session import HiveSession

_LOGGER = logging.getLogger(__name__)


class Hive(HiveSession):
    """Hive Class.

    Args:
        HiveSession (object): Interact with Hive Account
    """

    def __init__(
        self,
        websession: ClientSession | None = None,
        username: str | None = None,
        password: str | None = None,
    ):
        """Generate a Hive session.

        Args:
            websession (Optional[ClientSession], optional): Websession for API calls.
                Defaults to None.
            username (str, optional): This is the Hive username used for login. Defaults to None.
            password (str, optional): This is the Hive password used for login. Defaults to None.
        """
        super().__init__(username, password, websession)
        self.session = self
        self.action = HiveAction(self.session)
        self.heating = Climate(self.session)
        self.hotwater = WaterHeater(self.session)
        self.hub = HiveHub(self.session)
        self.light = Light(self.session)
        self.switch = Switch(self.session)
        self.sensor = Sensor(self.session)

    async def force_update(self) -> bool:
        """Immediately poll the Hive API, bypassing the 2-minute interval.

        For power users only. If a poll is already in progress, skips and
        returns False. Otherwise polls and returns True on success.
        """
        if self.update_lock.locked():
            _LOGGER.debug("force_update called while poll in progress — skipping.")
            return False
        async with self.update_lock:
            self._update_task = asyncio.current_task()
            try:
                return await self._poll_devices()
            finally:
                self._update_task = None
