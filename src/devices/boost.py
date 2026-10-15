"""Shared boost state helpers for heating and hot water."""

from __future__ import annotations

import logging
from typing import Any

from ..helper.const import HIVETOHA
from ..helper.hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)


class BoostMixin:
    """Read-only boost status helpers shared by HiveHeating and HiveHotwater.

    Expects ``self.session`` to be set by the owning class's ``__init__``.
    """

    session: Any

    async def get_boost_status(self, device: Device):
        """Get current boost status for the device.

        Returns:
            str: ``"ON"`` or ``"OFF"``, or None on error.
        """
        try:
            data = self.session.data.products[device.hive_id]
            return HIVETOHA["Boost"].get(data["state"].get("boost", False), "ON")
        except KeyError as e:
            _LOGGER.error("get_boost_status - KeyError for %s: %s", device.ha_name, e)
        return None

    async def get_boost_time(self, device: Device):
        """Get boost time remaining (minutes) when boost is active.

        Returns:
            int | None: Minutes remaining, or None when boost is not active.
        """
        if await self.get_boost_status(device) == "ON":
            try:
                data = self.session.data.products[device.hive_id]
                return data["state"]["boost"]
            except KeyError as e:
                _LOGGER.error("get_boost_time - KeyError for %s: %s", device.ha_name, e)
        return None
