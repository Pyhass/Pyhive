"""Polling and entity-cache mixin for HiveSession."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from aiohttp.web import HTTPException

from ..helper.hive_exceptions import HiveApiError, HiveAuthError, HiveReauthRequired
from ..helper.hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)


class PollingMixin:
    """Device polling, rate-limiting, and entity-cache methods.

    Expects ``self.config``, ``self.tokens``, ``self.api``,
    ``self.update_lock``, ``self._update_task``,
    ``self._last_poll_slow``, and ``self._slow_poll_threshold``
    to be set up by the owning class's ``__init__``.
    """

    # Attributes provided by HiveSession.__init__
    config: Any
    tokens: Any
    api: Any
    data: Any
    entity_cache: dict
    update_lock: asyncio.Lock
    _update_task: asyncio.Task | None
    _last_poll_slow: bool
    _slow_poll_threshold: int

    @staticmethod
    def _entity_cache_key(device) -> str:
        """Build a stable cache key for an entity instance."""
        return "|".join(
            [
                str(getattr(device, "ha_type", "")),
                str(getattr(device, "hive_id", "")),
                str(getattr(device, "hive_type", "")),
            ]
        )

    def get_cached_device(self, device):
        """Get cached state for a specific entity."""
        cache_key = self._entity_cache_key(device)
        return self.entity_cache.get(cache_key)

    def set_cached_device(self, device):
        """Store device state in cache and return it."""
        self.entity_cache[self._entity_cache_key(device)] = device
        return device

    def should_use_cached_data(self):
        """Determine whether callers should use cached entity state.

        Returns:
            bool: True when the last poll was slow or another task is currently polling.
        """
        if self._last_poll_slow:
            return True
        if self.update_lock.locked():
            current_task = asyncio.current_task()
            return self._update_task is None or current_task is not self._update_task
        return False

    async def _poll_devices(self) -> bool:
        """Fetch latest device state from the Hive API."""
        return await self.get_devices("No_ID")

    async def update_data(self, _device: Device):
        """Get latest data for Hive nodes - rate limiting.

        Args:
            _device (Device): Device requesting the update.

        Returns:
            boolean: True/False if update was successful
        """
        updated = False
        ep = self.config.last_update + self.config.scan_interval
        if datetime.now() >= ep:
            current_task = asyncio.current_task()
            if self.update_lock.locked() and (
                self._update_task is None or current_task is not self._update_task
            ):
                _LOGGER.debug("update_data - Update poll already in progress")
                return updated
            async with self.update_lock:
                # Re-check after acquiring lock — another caller may have already updated
                ep = self.config.last_update + self.config.scan_interval
                if datetime.now() < ep:
                    return updated
                self._update_task = current_task
                try:
                    _LOGGER.debug("Polling Hive API for device updates.")
                    updated = await self._poll_devices()
                    if updated:
                        _LOGGER.debug(
                            "update_data - Device update completed successfully."
                        )
                    else:
                        _LOGGER.debug(
                            "update_data - Device update failed, will retry after scan interval."
                        )
                finally:
                    if self._update_task is current_task:
                        self._update_task = None

        return updated

    async def get_devices(self, _n_id: str):  # pylint: disable=too-many-locals,too-many-statements  # noqa: PLR0912, PLR0915
        """Get latest data for Hive nodes.

        Args:
            _n_id (str): ID of the device requesting data.

        Raises:
            HTTPException: HTTP error has occurred updating the devices.
            HiveApiError: An API error code has been returned.

        Returns:
            boolean: True/False if update was successful.
        """
        get_nodes_successful = False
        api_resp_d = None

        try:
            if self.config.file:
                _LOGGER.debug("get_devices - Loading device data from file.")
                api_resp_d = self.open_file("data.json")  # type: ignore[attr-defined]
            elif self.tokens is not None:
                _LOGGER.debug(
                    "get_devices - Refreshing tokens before fetching devices."
                )
                await self.hive_refresh_tokens()  # type: ignore[attr-defined]
                _LOGGER.debug("get_devices - Fetching all devices from Hive API.")
                api_call_start = time.monotonic()
                try:
                    api_resp_d = await self.api.get_all()
                    api_call_duration = time.monotonic() - api_call_start
                    if api_call_duration > self._slow_poll_threshold:
                        _LOGGER.debug(
                            "get_devices - Hive API response took %.1fs — marking poll as slow.",
                            api_call_duration,
                        )
                        self._last_poll_slow = True
                    else:
                        self._last_poll_slow = False
                except HiveAuthError:
                    self._last_poll_slow = False
                    _LOGGER.warning(
                        "Auth error (401/403) after token refresh, "
                        "falling back to full device re-login."
                    )
                    await self._retry_login()  # type: ignore[attr-defined]
                    api_resp_d = await self._retry_with_backoff(  # type: ignore[attr-defined]
                        self.api.get_all,
                        reraise_as=HiveReauthRequired,
                    )
                if api_resp_d is None:
                    return get_nodes_successful
                if not str(api_resp_d["original"]).startswith("2"):
                    raise HTTPException
                if api_resp_d["parsed"] is None:
                    raise HiveApiError

            if api_resp_d is None:
                return get_nodes_successful
            api_resp_p = api_resp_d["parsed"]
            tmp_products = {}
            tmp_devices = {}
            tmp_actions = {}

            for hive_type_key in api_resp_p:
                if hive_type_key == "user":
                    self.data.user = api_resp_p[hive_type_key]
                    self.config.user_id = api_resp_p[hive_type_key].get("id")
                if hive_type_key == "products":
                    for a_product in api_resp_p[hive_type_key]:
                        tmp_products.update({a_product["id"]: a_product})
                if hive_type_key == "devices":
                    for a_device in api_resp_p[hive_type_key]:
                        tmp_devices.update({a_device["id"]: a_device})
                if hive_type_key == "actions":
                    for a_action in api_resp_p[hive_type_key]:
                        tmp_actions.update({a_action["id"]: a_action})
                if hive_type_key == "homes":
                    homes_data = api_resp_p[hive_type_key]
                    if isinstance(homes_data, dict):
                        homes_list = homes_data.get("homes") or []
                        if homes_list:
                            self.config.home_id = homes_list[0]["id"]

            _LOGGER.debug(
                "get_devices - API returned %d products, %d devices, %d actions.",
                len(tmp_products),
                len(tmp_devices),
                len(tmp_actions),
            )
            if tmp_products:
                self.data.products = tmp_products
            if tmp_devices:
                self.data.devices = tmp_devices
            self.data.actions = tmp_actions
            self.config.last_update = datetime.now()
            get_nodes_successful = True
        except HiveReauthRequired:
            _LOGGER.error("Reauthentication required, propagating to caller.")
            self.config.last_update = datetime.now()
            raise
        except asyncio.TimeoutError:
            _LOGGER.warning("Hive API request timed out — keeping cached device data.")
            self._last_poll_slow = True
            self.config.last_update = (
                datetime.now() - self.config.scan_interval + timedelta(seconds=30)
            )
            get_nodes_successful = False
        except (
            OSError,
            RuntimeError,
            HiveApiError,
            ConnectionError,
            HTTPException,
            KeyError,
        ) as err:
            _LOGGER.error("Failed to fetch devices: %s", err)
            self.config.last_update = (
                datetime.now() - self.config.scan_interval + timedelta(seconds=30)
            )
            get_nodes_successful = False

        return get_nodes_successful
