"""Hive API Module."""

# pylint: skip-file
import json
import logging
import re

import requests
import urllib3
from pyquery import PyQuery

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

_LOGGER = logging.getLogger(__name__)

# The SSO bootstrap page embeds its config as `window.<key> = <value>`
# assignments. The value quoting changed from double to single quotes on
# 2026-10-20, so accept either (and require the closing quote to match).
_SSO_ASSIGNMENT = re.compile(r"""window\.(\w+)\s*=\s*(["'])(.*?)\2""")


class HiveApi:
    """Hive API Code."""

    def __init__(self, hiveSession=None, websession=None, token=None):
        """Hive API initialisation."""
        self.cameraBaseUrl = "prod.hcam.bgchtest.info"
        self.urls = {
            "properties": "https://sso.hivehome.com/",
            "login": "https://beekeeper.hivehome.com/1.0/cognito/login",
            "refresh": "https://beekeeper.hivehome.com/1.0/cognito/refresh-token",
            "long_lived": "https://api.prod.bgchprod.info/omnia/accessTokens",
            "base": "https://beekeeper-uk.hivehome.com/1.0",
            "weather": "https://weather.prod.bgchprod.info/weather",
            "holiday_mode": "/holiday-mode",
            "all": "/nodes/all?products=true&devices=true&actions=true",
            "alarm": "/security-lite?homeId=",
            "cameraImages": f"https://event-history-service.{self.cameraBaseUrl}/v1/events/cameras?latest=true&cameraId={{0}}",
            "cameraRecordings": f"https://event-history-service.{self.cameraBaseUrl}/v1/playlist/cameras/{{0}}/events/{{1}}.m3u8",
            "devices": "/devices",
            "products": "/products",
            "actions": "/actions",
            "nodes": "/nodes/{0}/{1}",
        }
        self.timeout = 5
        self.json_return = {
            "original": "No response to Hive API request",
            "parsed": "No response to Hive API request",
        }
        self.session = hiveSession
        self.token = token

    def request(self, type, url, jsc=None, camera=False):
        """Make API request."""
        _LOGGER.debug("request - Making %s request to: %s", type, url)
        if jsc:
            _LOGGER.debug("request - Request payload: %s", jsc)

        if self.session is not None:
            if camera:
                self.headers = {
                    "content-type": "application/json",
                    "Accept": "*/*",
                    "Authorization": f"Bearer {self.session.tokens.tokenData['token']}",
                    "x-jwt-token": self.session.tokens.tokenData["token"],
                }
            else:
                self.headers = {
                    "content-type": "application/json",
                    "Accept": "*/*",
                    "authorization": self.session.tokens.tokenData["token"],
                }
        else:
            if camera:
                self.headers = {
                    "content-type": "application/json",
                    "Accept": "*/*",
                    "Authorization": f"Bearer {self.token}",
                    "x-jwt-token": self.token,
                }
            else:
                self.headers = {
                    "content-type": "application/json",
                    "Accept": "*/*",
                    "authorization": self.token,
                }

        _LOGGER.debug(
            "request - Request headers: %s",
            {k: v for k, v in self.headers.items() if k.lower() != "authorization"},
        )

        try:
            if type == "GET":
                return requests.get(
                    url=url, headers=self.headers, data=jsc, timeout=self.timeout
                )
            if type == "POST":
                return requests.post(
                    url=url, headers=self.headers, data=jsc, timeout=self.timeout
                )
        except Exception as e:
            _LOGGER.error("Request failed: %s", e)
            raise

    def refreshTokens(self, tokens={}):
        """Get new session tokens - DEPRECATED NOW BY AWS TOKEN MANAGEMENT."""
        _LOGGER.debug("refreshTokens - Attempting token refresh (deprecated method)")
        url = self.urls["refresh"]
        if self.session is not None:
            tokens = self.session.tokens.tokenData
        jsc = (
            "{"
            + ",".join(
                ('"' + str(i) + '": "' + str(t) + '" ' for i, t in tokens.items())
            )
            + "}"
        )
        try:
            info = self.request("POST", url, jsc)
            data = json.loads(info.text)
            if "token" in data and self.session:
                _LOGGER.debug(
                    "refreshTokens - Token refresh successful, updating session"
                )
                self.session.updateTokens(data)
                self.urls.update({"base": data["platform"]["endpoint"]})
                self.urls.update({"camera": data["platform"]["cameraPlatform"]})
            self.json_return.update({"original": info.status_code})
            self.json_return.update({"parsed": info.json()})
        except (OSError, RuntimeError, ZeroDivisionError, json.JSONDecodeError) as e:
            _LOGGER.error("Token refresh failed: %s", str(e))
            self.error()

        return self.json_return

    def getLoginInfo(self):
        """Get login properties to make the login request."""
        _LOGGER.debug(
            "getLoginInfo - Fetching login info from: %s", self.urls["properties"]
        )
        url = self.urls["properties"]
        try:
            data = requests.get(url=url, verify=False, timeout=self.timeout)
            _LOGGER.debug(
                "getLoginInfo - Login info response status: %s", data.status_code
            )
            html = PyQuery(data.content)
            json_data = {
                key: value
                for key, _quote, value in _SSO_ASSIGNMENT.findall(
                    html("script:first").text()
                )
            }

            loginData = {}
            loginData.update({"UPID": json_data["HiveSSOPoolId"]})
            loginData.update({"CLIID": json_data["HiveSSOPublicCognitoClientId"]})
            loginData.update({"REGION": json_data["HiveSSOPoolId"]})
            _LOGGER.debug("getLoginInfo - Login info extracted successfully")
            return loginData
        except (
            OSError,
            RuntimeError,
            ZeroDivisionError,
            json.JSONDecodeError,
            KeyError,
        ) as e:
            _LOGGER.error("Failed to get login info: %s", str(e))
            self.error()

    def getAll(self):
        """Build and query all endpoint."""
        _LOGGER.debug("getAll - Fetching all devices/products/actions from Hive API")
        json_return = {}
        url = self.urls["base"] + self.urls["all"]
        try:
            info = self.request("GET", url)
            if info is not None:
                json_return.update({"original": info.status_code})
                json_return.update({"parsed": info.json()})
                _LOGGER.debug(
                    "getAll - All data fetch successful, status: %s", info.status_code
                )
            else:
                _LOGGER.error("Failed to get response from all endpoint")
        except (OSError, RuntimeError, ZeroDivisionError, json.JSONDecodeError) as e:
            _LOGGER.error("Failed to fetch all data: %s", str(e))
            self.error()

        return json_return

    def getAlarm(self, homeID=None):
        """Build and query alarm endpoint."""
        if self.session is not None:
            homeID = self.session.config.homeID
        url = self.urls["base"] + self.urls["alarm"] + homeID
        try:
            info = self.request("GET", url)
            self.json_return.update({"original": info.status_code})
            self.json_return.update({"parsed": info.json()})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return self.json_return

    def getCameraImage(self, device=None, accessToken=None):
        """Build and query camera endpoint."""
        json_return = {}
        url = self.urls["cameraImages"].format(device["props"]["hardwareIdentifier"])
        try:
            info = self.request("GET", url, camera=True)
            json_return.update({"original": info.status_code})
            json_return.update({"parsed": info.json()})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return json_return

    def getCameraRecording(self, device=None, eventId=None):
        """Build and query camera endpoint."""
        json_return = {}
        url = self.urls["cameraRecordings"].format(
            device["props"]["hardwareIdentifier"], eventId
        )
        try:
            info = self.request("GET", url, camera=True)
            json_return.update({"original": info.status_code})
            json_return.update({"parsed": info.text.split("\n")[3]})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return json_return

    def getDevices(self):
        """Call the get devices endpoint."""
        url = self.urls["base"] + self.urls["devices"]
        try:
            response = self.request("GET", url)
            self.json_return.update({"original": response.status_code})
            self.json_return.update({"parsed": response.json()})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return self.json_return

    def getProducts(self):
        """Call the get products endpoint."""
        url = self.urls["base"] + self.urls["products"]
        try:
            response = self.request("GET", url)
            self.json_return.update({"original": response.status_code})
            self.json_return.update({"parsed": response.json()})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return self.json_return

    def getActions(self):
        """Call the get actions endpoint."""
        url = self.urls["base"] + self.urls["actions"]
        try:
            response = self.request("GET", url)
            self.json_return.update({"original": response.status_code})
            self.json_return.update({"parsed": response.json()})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return self.json_return

    def motionSensor(self, sensor, fromepoch, toepoch):
        """Call a way to get motion sensor info."""
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
            response = self.request("GET", url)
            self.json_return.update({"original": response.status_code})
            self.json_return.update({"parsed": response.json()})
        except (OSError, RuntimeError, ZeroDivisionError):
            self.error()

        return self.json_return

    def getWeather(self, weather_url):
        """Call endpoint to get local weather from Hive API."""
        t_url = self.urls["weather"] + weather_url
        url = t_url.replace(" ", "%20")
        try:
            response = self.request("GET", url)
            self.json_return.update({"original": response.status_code})
            self.json_return.update({"parsed": response.json()})
        except (OSError, RuntimeError, ZeroDivisionError, ConnectionError):
            self.error()

        return self.json_return

    def setState(self, n_type, n_id, **kwargs):
        """Set the state of a Device."""
        _LOGGER.debug(
            "setState - Setting state for device %s (type: %s): %s",
            n_id,
            n_type,
            kwargs,
        )
        jsc = (
            "{"
            + ",".join(
                ('"' + str(i) + '": "' + str(t) + '" ' for i, t in kwargs.items())
            )
            + "}"
        )

        url = self.urls["base"] + self.urls["nodes"].format(n_type, n_id)

        try:
            response = self.request("POST", url, jsc)
            if response is not None:
                self.json_return.update({"original": response.status_code})
                self.json_return.update({"parsed": response.json()})
                _LOGGER.debug(
                    "setState - State set successfully for %s, status: %s",
                    n_id,
                    response.status_code,
                )
            else:
                _LOGGER.error("Failed to set state for %s - no response", n_id)
        except (
            OSError,
            RuntimeError,
            ZeroDivisionError,
            ConnectionError,
            json.JSONDecodeError,
        ) as e:
            _LOGGER.error("Failed to set state for %s: %s", n_id, str(e))
            self.error()

        return self.json_return

    def setAction(self, n_id, data):
        """Set the state of a Action."""
        jsc = data
        url = self.urls["base"] + self.urls["actions"] + "/" + n_id
        try:
            response = self.request("POST", url, jsc)
            self.json_return.update({"original": response.status_code})
            self.json_return.update({"parsed": response.json()})
        except (OSError, RuntimeError, ZeroDivisionError, ConnectionError):
            self.error()

        return self.json_return

    def error(self):
        """An error has occurred interacting with the Hive API."""
        _LOGGER.error("API error occurred - returning error response")
        self.json_return.update({"original": "Error making API call"})
        self.json_return.update({"parsed": "Error making API call"})


class UnknownConfig(Exception):
    """Unknown API config."""
