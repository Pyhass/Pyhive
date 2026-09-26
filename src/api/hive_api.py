"""Hive API Module."""

import json
import logging
import re

import requests
from pyquery import PyQuery

from ..helper.hive_exceptions import HiveConnectionError

_LOGGER = logging.getLogger(__name__)

_NO_RESPONSE = "No response to Hive API request"
_ERROR_RESPONSE = "Error making API call"

# requests exceptions all subclass OSError; response.json() raises a
# json.JSONDecodeError subclass.
_REQUEST_ERRORS = (OSError, RuntimeError, json.JSONDecodeError)

_SSO_ASSIGNMENT = re.compile(r'window\.(\w+)\s*=\s*"([^"]*)"')


class HiveApi:
    """Hive API Code."""

    def __init__(self, hive_session=None, token=None):
        """Hive API initialisation."""
        self.urls = {
            "properties": "https://sso.hivehome.com/",
            "login": "https://beekeeper.hivehome.com/1.0/cognito/login",
            "refresh": "https://beekeeper.hivehome.com/1.0/cognito/refresh-token",
            "long_lived": "https://api.prod.bgchprod.info/omnia/accessTokens",
            "base": "https://beekeeper-uk.hivehome.com/1.0",
            "weather": "https://weather.prod.bgchprod.info/weather",
            "holiday_mode": "/holiday-mode",
            "all": "/nodes/all?products=true&devices=true&actions=true",
            "devices": "/devices",
            "products": "/products",
            "actions": "/actions",
            "nodes": "/nodes/{0}/{1}",
        }
        self.timeout = 5
        self.json_return = {
            "original": _NO_RESPONSE,
            "parsed": _NO_RESPONSE,
        }
        self.session = hive_session
        self.token = token
        self.headers = {
            "content-type": "application/json",
            "Accept": "*/*",
            "authorization": "",
        }

    def request(self, http_method, url, jsc=None):
        """Make API request."""
        _LOGGER.debug("request - Making %s request to: %s", http_method, url)
        if jsc:
            _LOGGER.debug("request - Request payload: %s", jsc)

        if self.session is not None:
            self.headers["authorization"] = self.session.tokens.token_data["token"]
        else:
            self.headers["authorization"] = self.token

        _LOGGER.debug(
            "request - Request headers: %s",
            {k: v for k, v in self.headers.items() if k.lower() != "authorization"},
        )

        try:
            if http_method == "GET":
                return requests.get(
                    url=url, headers=self.headers, data=jsc, timeout=self.timeout
                )
            if http_method == "POST":
                return requests.post(
                    url=url, headers=self.headers, data=jsc, timeout=self.timeout
                )
            raise ValueError(f"Unsupported request type: {http_method}")
        except Exception as e:
            _LOGGER.error("Request failed: %s", e)
            raise

    def _call_endpoint(self, http_method, url, jsc=None):
        """Call an endpoint and return a fresh result dict for this call."""
        json_return = {
            "original": _NO_RESPONSE,
            "parsed": _NO_RESPONSE,
        }
        try:
            response = self.request(http_method, url, jsc)
            if response is not None:
                json_return["original"] = response.status_code
                json_return["parsed"] = response.json()
            else:
                _LOGGER.error("No response from Hive API call to %s", url)
        except _REQUEST_ERRORS as e:
            _LOGGER.error("Hive API call to %s failed: %s", url, e)
            json_return = self.error()

        return json_return

    def get_login_info(self):
        """Get login properties to make the login request."""
        _LOGGER.debug(
            "get_login_info - Fetching login info from: %s", self.urls["properties"]
        )
        url = self.urls["properties"]
        try:
            data = requests.get(url=url, timeout=self.timeout)
            _LOGGER.debug(
                "get_login_info - Login info response status: %s", data.status_code
            )
            script_text = PyQuery(data.content)("script:first").text()
            sso_values = dict(_SSO_ASSIGNMENT.findall(script_text))

            login_data = {
                "UPID": sso_values["HiveSSOPoolId"],
                "CLIID": sso_values["HiveSSOPublicCognitoClientId"],
                "REGION": sso_values["HiveSSOPoolId"],
            }
            _LOGGER.debug("get_login_info - Login info extracted successfully")
            return login_data
        except OSError as e:
            # requests' timeouts and connection errors are OSError subclasses.
            _LOGGER.error("Failed to get login info: %s", str(e))
            self.error()
            raise HiveConnectionError("Could not reach the Hive login page") from e
        except (RuntimeError, KeyError) as e:
            _LOGGER.error("Failed to get login info: %s", str(e))
            self.error()
            return None

    def get_all(self):
        """Build and query all endpoint."""
        _LOGGER.debug("get_all - Fetching all devices/products/actions from Hive API")
        url = self.urls["base"] + self.urls["all"]
        return self._call_endpoint("GET", url)

    def get_devices(self):
        """Call the get devices endpoint."""
        url = self.urls["base"] + self.urls["devices"]
        return self._call_endpoint("GET", url)

    def get_products(self):
        """Call the get products endpoint."""
        url = self.urls["base"] + self.urls["products"]
        return self._call_endpoint("GET", url)

    def get_actions(self):
        """Call the get actions endpoint."""
        url = self.urls["base"] + self.urls["actions"]
        return self._call_endpoint("GET", url)

    def motion_sensor(self, sensor, fromepoch, toepoch):
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
        return self._call_endpoint("GET", url)

    def get_weather(self, weather_url):
        """Call endpoint to get local weather from Hive API."""
        t_url = self.urls["weather"] + weather_url
        url = t_url.replace(" ", "%20")
        return self._call_endpoint("GET", url)

    def set_state(self, n_type, n_id, **kwargs):
        """Set the state of a Device."""
        _LOGGER.debug(
            "set_state - Setting state for device %s (type: %s): %s",
            n_id,
            n_type,
            kwargs,
        )
        jsc = json.dumps(kwargs)
        url = self.urls["base"] + self.urls["nodes"].format(n_type, n_id)
        return self._call_endpoint("POST", url, jsc)

    def set_action(self, n_id, data):
        """Set the state of a Action."""
        jsc = data
        url = self.urls["base"] + self.urls["actions"] + "/" + n_id
        return self._call_endpoint("POST", url, jsc)

    def error(self):
        """An error has occurred interacting with the Hive API."""
        _LOGGER.error("API error occurred - returning error response")
        error_return = {
            "original": _ERROR_RESPONSE,
            "parsed": _ERROR_RESPONSE,
        }
        # Kept in sync for backwards compatibility with callers that read
        # the last error state off the instance.
        self.json_return.update(error_return)
        return error_return


class UnknownConfig(Exception):
    """Unknown API config."""
