"""Shared base class for all Hive device handlers."""

import logging
from typing import Any

from .const import HIVETOHA, HTTP_OK
from .hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)


class BaseDeviceHandler:  # pylint: disable=too-few-public-methods
    """Common plumbing shared across all Hive device handler classes.

    Subclasses must ensure ``self.session`` is set before any method is called.
    """

    session: Any

    async def _execute_state_change(self, device: Device, **state_kwargs) -> bool:
        """Check online → refresh tokens → set_state → get_devices.

        Returns True on HTTP 200, False on failure or when device is
        unavailable.  Uses the product type stored in session.data so callers
        never need to read it themselves.
        """
        if device.hive_id not in self.session.data.products:
            _LOGGER.debug(
                "_execute_state_change - %s not found in products", device.ha_name
            )
            return False
        if not (
            isinstance(device.device_data, dict) and device.device_data.get("online")
        ):
            _LOGGER.debug(
                "_execute_state_change - %s is offline or device_data not initialised",
                device.ha_name,
            )
            return False
        await self.session.hive_refresh_tokens()
        data = self.session.data.products[device.hive_id]
        resp = await self.session.api.set_state(
            data["type"], device.hive_id, **state_kwargs
        )
        if resp["original"] == HTTP_OK:
            await self.session.get_devices(device.hive_id)
            return True
        _LOGGER.error(
            "_execute_state_change - set_state failed for %s: HTTP %s",
            device.ha_name,
            resp["original"],
        )
        return False

    def _get_product_state(self, device: Device, *path_keys, default=None):
        """Read a nested value from session.data.products[device.hive_id].

        Returns *default* (None by default) if any key in *path_keys* is
        missing rather than raising KeyError.
        """
        try:
            node = self.session.data.products[device.hive_id]
            for key in path_keys:
                node = node[key]
            return node
        except (KeyError, TypeError):
            return default

    def _map_hive_to_ha(self, mapping_key: str, value, fallback=None):
        """Translate a raw Hive API value through HIVETOHA[mapping_key].

        Returns *fallback* when the key is absent from the mapping, or the
        original *value* when *fallback* is None.
        """
        mapping = HIVETOHA.get(mapping_key, {})
        if value in mapping:
            return mapping[value]
        return fallback if fallback is not None else value
