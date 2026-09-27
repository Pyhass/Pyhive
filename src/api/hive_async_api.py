"""Hive API Module."""

import asyncio
import json
import logging
import time

from aiohttp import (
    ClientError,
    ClientResponse,
    ClientSession,
    ClientTimeout,
    web_exceptions,
)

from ..helper.const import HTTP_FORBIDDEN, HTTP_UNAUTHORIZED
from ..helper.hive_exceptions import FileInUse, HiveApiError, HiveAuthError, NoApiToken

_LOGGER = logging.getLogger(__name__)

_REQUEST_ERRORS = (ClientError, OSError, RuntimeError, json.JSONDecodeError)


class HiveApiAsync:
    """Hive API Code."""

    def __init__(self, hive_session=None, websession: ClientSession | None = None):
        """Hive API initialisation."""
        self.base_url = "https://beekeeper.hivehome.com/1.0"
        self.urls = {
            "properties": "https://sso.hivehome.com/",
            "login": f"{self.base_url}/cognito/login",
            "refresh": f"{self.base_url}/cognito/refresh-token",
            "holiday_mode": f"{self.base_url}/holiday-mode",
            "all": f"{self.base_url}/nodes/all?products=true&devices=true&actions=true",
            "devices": f"{self.base_url}/devices",
            "products": f"{self.base_url}/products",
            "actions": f"{self.base_url}/actions",
            "nodes": f"{self.base_url}/nodes/{{0}}/{{1}}",
            "long_lived": "https://api.prod.bgchprod.info/omnia/accessTokens",
            "weather": "https://weather.prod.bgchprod.info/weather",
        }
        self.timeout = 5
        self.json_return = {
            "original": "No response to Hive API request",
            "parsed": "No response to Hive API request",
        }
        self.session = hive_session
        self.websession = websession

    def _get_websession(self) -> ClientSession:
        """Return the shared ClientSession, creating it on first use.

        Created lazily so the session is constructed inside a running
        event loop rather than in the synchronous constructor.
        """
        if self.websession is None:
            self.websession = ClientSession()
        return self.websession

    async def request(self, method: str, url: str, **kwargs) -> ClientResponse:
        """Make a request."""
        _LOGGER.debug("API %s request to %s", method.upper(), url)
        data = kwargs.get("data", None)

        headers = {
            "content-type": "application/json",
            "Accept": "*/*",
            "User-Agent": "Hive/12.04.0 iOS/18.3.1 Apple",
        }
        try:
            headers["Authorization"] = self.session.tokens.token_data["token"]
        except KeyError as exc:
            if "sso" in url:
                pass
            else:
                raise NoApiToken from exc

        auth_token = headers.get("Authorization", "")
        _LOGGER.debug(
            "Using token (len=%d, tail=…%s)",
            len(auth_token),
            auth_token[-4:] if len(auth_token) >= 4 else auth_token,  # noqa: PLR2004
        )

        timeout = ClientTimeout(total=self.timeout)
        req_start = time.monotonic()
        async with self._get_websession().request(
            method, url, headers=headers, data=data, timeout=timeout
        ) as resp:
            resp_body = await resp.text()
            req_duration = time.monotonic() - req_start
            _LOGGER.debug(
                "API %s %s completed in %.2fs — HTTP %s",
                method.upper(),
                url,
                req_duration,
                resp.status,
            )
            if str(resp.status).startswith("20"):
                return resp

        if resp.status in (HTTP_UNAUTHORIZED, HTTP_FORBIDDEN):
            _LOGGER.error(
                "Hive token rejected calling %s - HTTP %s — response: %s",
                url,
                resp.status,
                resp_body[:200],
            )
            raise HiveAuthError(
                f"Token expired or forbidden calling {url} — HTTP {resp.status}"
            )
        _LOGGER.error(
            "Something has gone wrong calling %s - HTTP status is - %s — response: %s",
            url,
            resp.status,
            resp_body[:200],
        )
        raise HiveApiError

    async def _call_endpoint(self, method: str, url: str, data=None) -> dict:
        """Call an endpoint and return {"original": status, "parsed": json}."""
        json_return: dict = {}
        try:
            resp = await self.request(method, url, data=data)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except asyncio.TimeoutError:
            _LOGGER.warning("Hive API request timed out calling %s", url)
            raise
        except _REQUEST_ERRORS:
            await self.error()

        return json_return

    async def get_all(self):
        """Build and query all endpoint."""
        return await self._call_endpoint("get", self.urls["all"])

    async def get_devices(self):
        """Call the get devices endpoint."""
        return await self._call_endpoint("get", self.urls["devices"])

    async def get_products(self):
        """Call the get products endpoint."""
        return await self._call_endpoint("get", self.urls["products"])

    async def get_actions(self):
        """Call the get actions endpoint."""
        return await self._call_endpoint("get", self.urls["actions"])

    async def motion_sensor(self, sensor, fromepoch, toepoch):
        """Call a way to get motion sensor info."""
        url = (
            self.base_url
            + "/products"
            + "/"
            + sensor["type"]
            + "/"
            + sensor["id"]
            + "/events?from="
            + str(fromepoch)
            + "&to="
            + str(toepoch)
        )
        return await self._call_endpoint("get", url)

    async def get_weather(self, weather_url):
        """Call endpoint to get local weather from Hive API."""
        t_url = self.urls["weather"] + weather_url
        url = t_url.replace(" ", "%20")
        return await self._call_endpoint("get", url)

    async def set_state(self, n_type, n_id, **kwargs):
        """Set the state of a Device."""
        _LOGGER.debug("set_state - Setting state for %s/%s: %s", n_type, n_id, kwargs)
        jsc = json.dumps(kwargs)
        url = self.urls["nodes"].format(n_type, n_id)
        try:
            await self.is_file_being_used()
        except FileInUse:
            return {"original": "file"}
        return await self._call_endpoint("post", url, data=jsc)

    async def set_action(self, n_id, data):
        """Set the state of a Action."""
        _LOGGER.debug("Setting action %s", n_id)
        url = self.urls["actions"] + "/" + n_id
        try:
            await self.is_file_being_used()
        except FileInUse:
            return {"original": "file"}
        return await self._call_endpoint("put", url, data=data)

    async def get_holiday_mode(self):
        """Get the current holiday mode configuration."""
        return await self._call_endpoint("get", self.urls["holiday_mode"])

    async def set_holiday_mode(self, start: int, end: int, temperature: float):
        """Schedule holiday mode.

        Args:
            start: Start time as epoch milliseconds.
            end: End time as epoch milliseconds.
            temperature: Frost-protection temperature to hold during holiday mode.
        """
        _LOGGER.debug(
            "set_holiday_mode - Scheduling holiday mode from %s to %s at %s°.",
            start,
            end,
            temperature,
        )
        jsc = json.dumps({"start": start, "end": end, "temperature": temperature})
        try:
            await self.is_file_being_used()
        except FileInUse:
            return {"original": "file"}
        return await self._call_endpoint("post", self.urls["holiday_mode"], data=jsc)

    async def cancel_holiday_mode(self):
        """Cancel any scheduled or active holiday mode."""
        _LOGGER.debug("cancel_holiday_mode - Cancelling holiday mode.")
        try:
            await self.is_file_being_used()
        except FileInUse:
            return {"original": "file"}
        return await self._call_endpoint(
            "delete", self.urls["holiday_mode"], data=json.dumps({})
        )

    async def error(self):
        """An error has occurred interacting with the Hive API."""
        _LOGGER.error("HTTP error occurred during Hive API interaction.")
        raise web_exceptions.HTTPError

    async def is_file_being_used(self):
        """Check if running in file mode."""
        if self.session.config.file:
            raise FileInUse()
