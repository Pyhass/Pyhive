"""Hive API Module."""

# pylint: skip-file
import asyncio
import json
import logging
import time
from typing import Optional

import requests
import urllib3
from aiohttp import ClientResponse, ClientSession, ClientTimeout, web_exceptions
from pyquery import PyQuery

from ..helper.const import HTTP_FORBIDDEN, HTTP_UNAUTHORIZED
from ..helper.hive_exceptions import FileInUse, HiveApiError, HiveAuthError, NoApiToken

_LOGGER = logging.getLogger(__name__)

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HiveApiAsync:
    """Hive API Code."""

    def __init__(self, hiveSession=None, websession: Optional[ClientSession] = None):
        """Hive API initialisation."""
        self.baseUrl = "https://beekeeper.hivehome.com/1.0"
        self.cameraBaseUrl = "prod.hcam.bgchtest.info"
        self.urls = {
            "properties": "https://sso.hivehome.com/",
            "login": f"{self.baseUrl}/cognito/login",
            "refresh": f"{self.baseUrl}/cognito/refresh-token",
            "holiday_mode": f"{self.baseUrl}/holiday-mode",
            "all": f"{self.baseUrl}/nodes/all?products=true&devices=true&actions=true",
            "alarm": f"{self.baseUrl}/security-lite?homeId=",
            "cameraImages": f"https://event-history-service.{self.cameraBaseUrl}/v1/events/cameras?latest=true&cameraId={{0}}",
            "cameraRecordings": f"https://event-history-service.{self.cameraBaseUrl}/v1/playlist/cameras/{{0}}/events/{{1}}.m3u8",
            "devices": f"{self.baseUrl}/devices",
            "products": f"{self.baseUrl}/products",
            "actions": f"{self.baseUrl}/actions",
            "nodes": f"{self.baseUrl}/nodes/{{0}}/{{1}}",
            "long_lived": "https://api.prod.bgchprod.info/omnia/accessTokens",
            "weather": "https://weather.prod.bgchprod.info/weather",
        }
        self.timeout = 5
        self.json_return = {
            "original": "No response to Hive API request",
            "parsed": "No response to Hive API request",
        }
        self.session = hiveSession
        self.websession = ClientSession() if websession is None else websession

    async def request(
        self, method: str, url: str, camera: bool = False, **kwargs
    ) -> ClientResponse:
        """Make a request."""
        _LOGGER.debug("API %s request to %s", method.upper(), url)
        data = kwargs.get("data", None)

        headers = {
            "content-type": "application/json",
            "Accept": "*/*",
            "User-Agent": "Hive/12.04.0 iOS/18.3.1 Apple",
        }
        try:
            if camera:
                headers["Authorization"] = (
                    f"Bearer {self.session.tokens.tokenData['token']}"
                )
                headers["x-jwt-token"] = self.session.tokens.tokenData["token"]
            else:
                headers["Authorization"] = self.session.tokens.tokenData["token"]
        except KeyError:
            if "sso" in url:
                pass
            else:
                raise NoApiToken

        auth_token = headers.get("Authorization", "")
        _LOGGER.debug(
            "Using token (len=%d, tail=…%s)",
            len(auth_token),
            auth_token[-4:] if len(auth_token) >= 4 else auth_token,
        )

        timeout = ClientTimeout(total=self.timeout)
        req_start = time.monotonic()
        async with self.websession.request(
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
                f"Hive token rejected calling {url} - "
                f"HTTP {resp.status} — response: {resp_body[:200]}"
            )
            raise HiveAuthError(
                f"Token expired or forbidden calling {url} — HTTP {resp.status}"
            )
        elif url is not None and resp.status is not None:
            _LOGGER.error(
                f"Something has gone wrong calling {url} - "
                f"HTTP status is - {resp.status} — response: {resp_body[:200]}"
            )

        raise HiveApiError

    def getLoginInfo(self):
        """Get login properties to make the login request."""
        url = "https://sso.hivehome.com/"

        data = requests.get(url=url, verify=False, timeout=self.timeout)
        html = PyQuery(data.content)
        json_data = json.loads(
            '{"'
            + (html("script:first").text())
            .replace(",", ', "')
            .replace("=", '":')
            .replace("window.", "")
            + "}"
        )

        loginData = {}
        loginData.update({"UPID": json_data["HiveSSOPoolId"]})
        loginData.update({"CLIID": json_data["HiveSSOPublicCognitoClientId"]})
        loginData.update({"REGION": json_data["HiveSSOPoolId"]})
        return loginData

    async def refreshTokens(self):
        """Refresh tokens - DEPRECATED NOW BY AWS TOKEN MANAGEMENT."""
        url = self.urls["refresh"]
        if self.session is not None:
            tokens = self.session.tokens.tokenData
        jsc = (
            "{"
            + ",".join(
                ('"' + str(i) + '": ' '"' + str(t) + '" ' for i, t in tokens.items())
            )
            + "}"
        )
        try:
            await self.request("post", url, data=jsc)

            if self.json_return["original"] == 200:
                info = self.json_return["parsed"]
                if "token" in info:
                    await self.session.updateTokens(info)
                    self.baseUrl = info["platform"]["endpoint"]
                    self.cameraBaseUrl = info["platform"]["cameraPlatform"]
                return True
        except (ConnectionError, OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return self.json_return

    async def getAll(self):
        """Build and query all endpoint."""
        json_return = {}
        url = self.urls["all"]
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except asyncio.TimeoutError:
            _LOGGER.warning("Hive API request timed out fetching all nodes.")
            raise
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getAlarm(self):
        """Build and query alarm endpoint."""
        json_return = {}
        url = self.urls["alarm"] + self.session.config.homeID
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getCameraImage(self, device):
        """Build and query alarm endpoint."""
        json_return = {}
        url = self.urls["cameraImages"].format(device["props"]["hardwareIdentifier"])
        try:
            resp = await self.request("get", url, True)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getCameraRecording(self, device, eventId):
        """Build and query alarm endpoint."""
        json_return = {}
        url = self.urls["cameraRecordings"].format(
            device["props"]["hardwareIdentifier"], eventId
        )
        try:
            resp = await self.request("get", url, True)
            recUrl = await resp.text()
            json_return.update({"original": resp.status})
            json_return.update({"parsed": recUrl.split("\n")[3]})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getDevices(self):
        """Call the get devices endpoint."""
        json_return = {}
        url = self.urls["devices"]
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getProducts(self):
        """Call the get products endpoint."""
        json_return = {}
        url = self.urls["products"]
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getActions(self):
        """Call the get actions endpoint."""
        json_return = {}
        url = self.urls["actions"]
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def motionSensor(self, sensor, fromepoch, toepoch):
        """Call a way to get motion sensor info."""
        json_return = {}
        url = (
            self.urls["base"]
            + self.urls["products"]
            + "/"
            + sensor["type"]
            + "/"
            + sensor["id"]
            + "/events?from="
            + str(fromepoch)
            + "&to="
            + str(toepoch)
        )
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

    async def getWeather(self, weather_url):
        """Call endpoint to get local weather from Hive API."""
        json_return = {}
        t_url = self.urls["weather"] + weather_url
        url = t_url.replace(" ", "%20")
        try:
            resp = await self.request("get", url)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError, ConnectionError):
            await self.error()

        return json_return

    async def setState(self, n_type, n_id, **kwargs):
        """Set the state of a Device."""
        _LOGGER.debug("setState - Setting state for %s/%s: %s", n_type, n_id, kwargs)
        json_return = {}
        jsc = (
            "{"
            + ",".join(
                ('"' + str(i) + '": ' '"' + str(t) + '" ' for i, t in kwargs.items())
            )
            + "}"
        )

        url = self.urls["nodes"].format(n_type, n_id)
        try:
            await self.isFileBeingUsed()
            resp = await self.request("post", url, data=jsc)
            json_return["original"] = resp.status
            json_return["parsed"] = await resp.json(content_type=None)
        except (FileInUse, OSError, RuntimeError, ConnectionError) as e:
            if e.__class__.__name__ == "FileInUse":
                return {"original": "file"}
            else:
                await self.error()

        return json_return

    async def setAlarm(self, **kwargs):
        """Set the state of the alarm."""
        _LOGGER.debug("Setting alarm state: %s", kwargs)
        json_return = {}
        jsc = (
            "{"
            + ",".join(
                ('"' + str(i) + '": ' '"' + str(t) + '" ' for i, t in kwargs.items())
            )
            + "}"
        )

        url = f"{self.urls['alarm']}{self.session.config.homeID}"
        try:
            await self.isFileBeingUsed()
            resp = await self.request("post", url, data=jsc)
            json_return["original"] = resp.status
            json_return["parsed"] = await resp.json(content_type=None)
        except (FileInUse, OSError, RuntimeError, ConnectionError) as e:
            if e.__class__.__name__ == "FileInUse":
                return {"original": "file"}
            else:
                await self.error()

        return json_return

    async def setAction(self, n_id, data):
        """Set the state of a Action."""
        _LOGGER.debug("Setting action %s", n_id)
        jsc = data
        url = self.urls["actions"] + "/" + n_id
        try:
            await self.isFileBeingUsed()
            await self.request("put", url, data=jsc)
        except (FileInUse, OSError, RuntimeError, ConnectionError) as e:
            if e.__class__.__name__ == "FileInUse":
                return {"original": "file"}
            else:
                await self.error()

        return self.json_return

    async def get_holiday_mode(self):
        """Get the current holiday mode configuration."""
        json_return = {}
        try:
            resp = await self.request("get", self.urls["holiday_mode"])
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (OSError, RuntimeError, ZeroDivisionError):
            await self.error()

        return json_return

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
        json_return = {}
        jsc = json.dumps({"start": start, "end": end, "temperature": temperature})
        try:
            await self.isFileBeingUsed()
            resp = await self.request("post", self.urls["holiday_mode"], data=jsc)
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (FileInUse, OSError, RuntimeError, ConnectionError) as e:
            if e.__class__.__name__ == "FileInUse":
                return {"original": "file"}
            await self.error()

        return json_return

    async def cancel_holiday_mode(self):
        """Cancel any scheduled or active holiday mode."""
        _LOGGER.debug("cancel_holiday_mode - Cancelling holiday mode.")
        json_return = {}
        try:
            await self.isFileBeingUsed()
            resp = await self.request(
                "delete", self.urls["holiday_mode"], data=json.dumps({})
            )
            json_return.update({"original": resp.status})
            json_return.update({"parsed": await resp.json(content_type=None)})
        except (FileInUse, OSError, RuntimeError, ConnectionError) as e:
            if e.__class__.__name__ == "FileInUse":
                return {"original": "file"}
            await self.error()

        return json_return

    async def error(self):
        """An error has occurred interacting with the Hive API."""
        _LOGGER.error("HTTP error occurred during Hive API interaction.")
        raise web_exceptions.HTTPError

    async def isFileBeingUsed(self):
        """Check if running in file mode."""
        if self.session.config.file:
            raise FileInUse()
