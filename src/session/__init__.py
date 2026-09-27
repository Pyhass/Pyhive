"""Hive Session Module."""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import ClientSession
from apyhiveapi import API, Auth  # type: ignore[import-not-found]

from ..helper.compat_aliases import SessionCompatMixin
from ..helper.device_attributes import HiveAttributes
from ..helper.hive_helper import HiveHelper
from ..helper.hivedataclasses import Device, SessionConfig, SessionTokens
from ..helper.map import Map
from .auth import SessionAuthMixin
from .discovery import DiscoveryMixin
from .polling import PollingMixin


class HiveSession(SessionCompatMixin, SessionAuthMixin, PollingMixin, DiscoveryMixin):
    """Hive Session Code.

    Raises:
        HiveUnknownConfiguration: Unknown configuration.
        HTTPException: HTTP error has occurred.
        HiveApiError: Hive has returned an error code.
        HiveReauthRequired: Tokens have expired and reauthentication is required.

    Returns:
        object: Session object.
    """

    session_type = "Session"

    def __init__(
        self,
        username: str | None = None,
        password: str | None = None,
        websession: ClientSession | None = None,
    ) -> None:
        """Initialise the base variable values.

        Args:
            username (str, optional): Hive username. Defaults to None.
            password (str, optional): Hive Password. Defaults to None.
            websession (object, optional): Websession for api calls. Defaults to None.
        """
        self.auth = Auth(
            username=username,
            password=password,
        )
        self._owns_websession = websession is None
        self.api = API(hive_session=self, websession=websession)
        self.helper = HiveHelper(self)
        self.attr = HiveAttributes(self)
        self.update_lock = asyncio.Lock()
        self._refresh_lock = asyncio.Lock()
        self.tokens = SessionTokens()
        self.config = SessionConfig(username=username)
        self.data: Any = Map(
            {
                "products": {},
                "devices": {},
                "actions": {},
                "user": {},
                "minMax": {},
            }
        )
        self.entity_cache: dict[str, Device] = {}
        self.device_list: dict[str, list[Device]] = {}
        self.hub_id = None
        self._last_poll_slow = False
        self._slow_poll_threshold = 3
        self._refresh_threshold = 0.90
        self._update_task: asyncio.Task | None = None

    async def close(self) -> None:
        """Close the underlying aiohttp ClientSession if we own it."""
        websession = self.api.websession
        if self._owns_websession and websession is not None and not websession.closed:
            await websession.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_) -> None:
        await self.close()
