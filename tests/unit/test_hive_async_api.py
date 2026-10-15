"""Unit tests for HiveApiAsync."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from aiohttp import web_exceptions
from apyhiveapi.api.hive_async_api import HiveApiAsync
from apyhiveapi.helper.hive_exceptions import (
    FileInUse,
    HiveApiError,
    HiveAuthError,
    NoApiToken,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(status=200, json_data=None):
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value="")
    resp.json = AsyncMock(return_value=json_data or {"data": "test"})
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_mock_websession(status=200, json_data=None):
    resp = _make_mock_response(status=status, json_data=json_data)
    websession = MagicMock()
    websession.request.return_value = resp
    websession.closed = False
    websession.close = AsyncMock()
    return websession


def _make_api(status=200, json_data=None, token="test-token", file_mode=False):
    websession = _make_mock_websession(status=status, json_data=json_data)
    session = MagicMock()
    session.tokens = MagicMock()
    session.tokens.token_data = {"token": token}
    session.config = MagicMock()
    session.config.file = file_mode
    return HiveApiAsync(hive_session=session, websession=websession)


def _make_api_no_token(_url_contains_sso=False):
    """Return an API instance whose session raises KeyError on token lookup."""
    websession = _make_mock_websession(status=200)
    session = MagicMock()
    session.tokens = MagicMock()
    # Raise KeyError when "token" key is accessed
    session.tokens.token_data = {}
    session.config = MagicMock()
    session.config.file = False
    return HiveApiAsync(hive_session=session, websession=websession)


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.request
# ---------------------------------------------------------------------------


class TestHiveApiAsyncRequest:
    async def test_successful_200_returns_response(self):
        api = _make_api(status=200, json_data={"ok": True})
        resp = await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")
        assert resp.status == 200

    async def test_201_also_succeeds(self):
        api = _make_api(status=201)
        resp = await api.request("post", "https://beekeeper.hivehome.com/1.0/nodes/x/y")
        assert resp.status == 201

    async def test_sso_url_without_token_does_not_raise(self):
        api = _make_api_no_token()
        # Should not raise NoApiToken because "sso" is in the URL
        resp = await api.request("get", "https://sso.hivehome.com/")
        assert resp.status == 200

    async def test_non_sso_without_token_raises_no_api_token(self):
        api = _make_api_no_token()
        with pytest.raises(NoApiToken):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")

    async def test_401_raises_hive_auth_error(self):
        api = _make_api(status=401)
        with pytest.raises(HiveAuthError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")

    async def test_403_raises_hive_auth_error(self):
        api = _make_api(status=403)
        with pytest.raises(HiveAuthError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")

    async def test_500_raises_hive_api_error(self):
        api = _make_api(status=500)
        with pytest.raises(HiveApiError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")

    async def test_404_raises_hive_api_error(self):
        api = _make_api(status=404)
        with pytest.raises(HiveApiError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.get_all
# ---------------------------------------------------------------------------


class TestGetAll:
    async def test_successful_get_all_returns_parsed_json(self):
        payload = {"products": [], "devices": []}
        api = _make_api(status=200, json_data=payload)
        result = await api.get_all()
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_timeout_error_propagates(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = asyncio.TimeoutError
        with pytest.raises(asyncio.TimeoutError):
            await api.get_all()

    async def test_os_error_calls_error_method(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError("network down")
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_all()

    async def test_runtime_error_calls_error_method(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = RuntimeError("boom")
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_all()


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.get_devices / get_products / get_actions
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    async def test_get_devices_returns_parsed_json(self):
        payload = [{"id": "dev1"}]
        api = _make_api(status=200, json_data=payload)
        result = await api.get_devices()
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_get_products_returns_parsed_json(self):
        payload = [{"id": "prod1"}]
        api = _make_api(status=200, json_data=payload)
        result = await api.get_products()
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_get_actions_returns_parsed_json(self):
        payload = [{"id": "act1"}]
        api = _make_api(status=200, json_data=payload)
        result = await api.get_actions()
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_get_devices_os_error_raises_http_error(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_devices()

    async def test_get_products_os_error_raises_http_error(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_products()

    async def test_get_actions_os_error_raises_http_error(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_actions()


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.set_state
# ---------------------------------------------------------------------------


class TestSetState:
    async def test_file_in_use_returns_file_response(self):
        api = _make_api(status=200, file_mode=True)
        result = await api.set_state("heating", "node-1", mode="MANUAL")
        assert result == {"original": "file"}

    async def test_successful_set_state(self):
        payload = {"id": "node-1", "mode": "MANUAL"}
        api = _make_api(status=200, json_data=payload)
        result = await api.set_state("heating", "node-1", mode="MANUAL")
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_os_error_calls_error_method(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError("fail")
        with pytest.raises(web_exceptions.HTTPError):
            await api.set_state("heating", "node-1", mode="MANUAL")

    async def test_runtime_error_calls_error_method(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = RuntimeError("fail")
        with pytest.raises(web_exceptions.HTTPError):
            await api.set_state("heating", "node-1", mode="MANUAL")


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.set_action
# ---------------------------------------------------------------------------


class TestSetAction:
    async def test_file_in_use_returns_file_response(self):
        api = _make_api(status=200, file_mode=True)
        result = await api.set_action("action-1", '{"status": "on"}')
        assert result == {"original": "file"}

    async def test_successful_set_action_returns_status_200(self):
        payload = {"id": "action-1", "status": "on"}
        api = _make_api(status=200, json_data=payload)
        result = await api.set_action("action-1", '{"status": "on"}')
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_runtime_error_calls_error_method(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = RuntimeError("fail")
        with pytest.raises(web_exceptions.HTTPError):
            await api.set_action("action-1", "{}")

    async def test_os_error_calls_error_method(self):
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError
        with pytest.raises(web_exceptions.HTTPError):
            await api.set_action("action-1", "{}")


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync holiday mode
# ---------------------------------------------------------------------------


class TestHolidayMode:
    async def test_get_holiday_mode_returns_parsed_json(self):
        payload = {
            "active": False,
            "enabled": False,
            "start": 1783006500000,
            "end": 1783296000000,
            "temperature": 12,
            "status": "OK",
        }
        api = _make_api(status=200, json_data=payload)
        result = await api.get_holiday_mode()
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_set_holiday_mode_posts_epoch_ms_body(self):
        payload = {"start": 1783767707701, "end": 1784372507701, "temperature": 12}
        api = _make_api(status=200, json_data=payload)
        result = await api.set_holiday_mode(1783767707701, 1784372507701, 12)
        assert result["original"] == 200
        assert result["parsed"] == payload
        _, kwargs = api.websession.request.call_args
        assert json.loads(kwargs["data"]) == {
            "start": 1783767707701,
            "end": 1784372507701,
            "temperature": 12,
        }

    async def test_set_holiday_mode_file_in_use_returns_file_response(self):
        api = _make_api(status=200, file_mode=True)
        result = await api.set_holiday_mode(1, 2, 12)
        assert result == {"original": "file"}

    async def test_cancel_holiday_mode_returns_set_true(self):
        api = _make_api(status=200, json_data={"set": True})
        result = await api.cancel_holiday_mode()
        assert result["original"] == 200
        assert result["parsed"] == {"set": True}
        args, _ = api.websession.request.call_args
        assert args[0] == "delete"

    async def test_cancel_holiday_mode_file_in_use_returns_file_response(self):
        api = _make_api(status=200, file_mode=True)
        result = await api.cancel_holiday_mode()
        assert result == {"original": "file"}


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.motion_sensor
# ---------------------------------------------------------------------------


class TestMotionSensor:
    async def test_url_does_not_double_base_url(self):
        payload = [{"timestamp": 12345}]
        api = _make_api(status=200, json_data=payload)
        captured = {}
        original_request = api.request

        async def capture_request(method, url, **kwargs):
            captured["url"] = url
            return await original_request(method, url, **kwargs)

        api.request = capture_request
        sensor = {"type": "motionsensor", "id": "ms-001"}
        await api.motion_sensor(sensor, 1000000, 2000000)
        url = captured["url"]
        assert url.startswith(api.base_url + "/products/")
        assert "motionsensor/ms-001" in url
        assert url.count("https://beekeeper") == 1

    async def test_motion_sensor_returns_parsed_json(self):
        payload = [{"timestamp": 12345}]
        api = _make_api(status=200, json_data=payload)
        sensor = {"type": "motionsensor", "id": "ms-001"}
        result = await api.motion_sensor(sensor, 1000000, 2000000)
        assert result["original"] == 200
        assert result["parsed"] == payload


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.error
# ---------------------------------------------------------------------------


class TestError:
    async def test_error_raises_http_error(self):
        api = _make_api()
        with pytest.raises(web_exceptions.HTTPError):
            await api.error()


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.is_file_being_used
# ---------------------------------------------------------------------------


class TestIsFileBeingUsed:
    async def test_file_mode_raises_file_in_use(self):
        api = _make_api(file_mode=True)
        with pytest.raises(FileInUse):
            await api.is_file_being_used()

    async def test_not_file_mode_does_not_raise(self):
        api = _make_api(file_mode=False)
        await api.is_file_being_used()  # Should not raise


# ---------------------------------------------------------------------------
# Tests: HiveApiAsync.__init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_no_websession_created_at_init(self):
        """No ClientSession is created in the sync constructor."""
        session = MagicMock()
        session.tokens = MagicMock()
        session.tokens.token_data = {"token": "tok"}
        session.config = MagicMock()
        api = HiveApiAsync(hive_session=session)
        assert api.websession is None

    def test_websession_created_lazily_and_cached(self):
        """The first _get_websession() call creates and caches a ClientSession."""
        session = MagicMock()
        api = HiveApiAsync(hive_session=session)
        with patch("apyhiveapi.api.hive_async_api.ClientSession") as mock_session_cls:
            first = api._get_websession()
            second = api._get_websession()
        mock_session_cls.assert_called_once()
        assert first is mock_session_cls.return_value
        assert second is first
        assert api.websession is first

    def test_custom_websession_is_used(self):
        session = MagicMock()
        ws = MagicMock()
        api = HiveApiAsync(hive_session=session, websession=ws)
        assert api.websession is ws

    def test_base_url_is_set(self):
        api = _make_api()
        assert api.base_url == "https://beekeeper.hivehome.com/1.0"

    def test_default_timeout(self):
        api = _make_api()
        assert api.timeout == 5


# ---------------------------------------------------------------------------
# Migrated from test_hive_async_api_extended.py
# ---------------------------------------------------------------------------


class TestRequestNonAuthErrorBranch:
    """Cover lines 100-108: url/status not None branch leading to HiveApiError."""

    async def test_404_logs_and_raises_hive_api_error(self):
        """A 404 falls through to the url/status branch and raises HiveApiError."""
        api = _make_api(status=404)
        with pytest.raises(HiveApiError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")

    async def test_503_logs_and_raises_hive_api_error(self):
        """A 503 falls through to the url/status branch and raises HiveApiError."""
        api = _make_api(status=503)
        with pytest.raises(HiveApiError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/nodes/all")

    async def test_422_logs_and_raises_hive_api_error(self):
        """A 422 also falls through (not 401/403) and raises HiveApiError."""
        api = _make_api(status=422)
        with pytest.raises(HiveApiError):
            await api.request("get", "https://beekeeper.hivehome.com/1.0/devices")


class TestMotionSensorBranches:
    """Cover lines 215-235: motion_sensor() success and error paths."""

    async def test_success_returns_status_and_parsed(self):
        """Successful call returns status and parsed JSON."""
        payload = [{"event": "motion", "timestamp": 1234567890}]
        api = _make_api(status=200, json_data=payload)
        api.urls["base"] = ""
        sensor = {"type": "motionsensor", "id": "sensor-001"}
        result = await api.motion_sensor(sensor, fromepoch=1000000, toepoch=2000000)
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_url_is_built_correctly(self):
        """Verifies the URL is assembled with correct sensor type and id."""
        api = _make_api(status=200, json_data=[])
        api.urls["base"] = "https://beekeeper-uk.hivehome.com/1.0"
        sensor = {"type": "contactsensor", "id": "abc-123"}
        captured_url = []
        original_request = api.request

        async def capture_request(method, url, **kwargs):
            captured_url.append(url)
            return await original_request(method, url, **kwargs)

        with patch.object(api, "request", side_effect=capture_request):
            await api.motion_sensor(sensor, fromepoch=100, toepoch=200)
        assert len(captured_url) == 1
        assert "contactsensor" in captured_url[0]
        assert "abc-123" in captured_url[0]
        assert "from=100" in captured_url[0]
        assert "to=200" in captured_url[0]

    async def test_os_error_raises_http_error(self):
        """OSError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.urls["base"] = ""
        sensor = {"type": "motionsensor", "id": "sensor-001"}
        api.websession.request.side_effect = OSError("fail")
        with pytest.raises(web_exceptions.HTTPError):
            await api.motion_sensor(sensor, fromepoch=1000, toepoch=2000)

    async def test_runtime_error_raises_http_error(self):
        """RuntimeError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.urls["base"] = ""
        sensor = {"type": "motionsensor", "id": "sensor-002"}
        api.websession.request.side_effect = RuntimeError("unexpected")
        with pytest.raises(web_exceptions.HTTPError):
            await api.motion_sensor(sensor, fromepoch=1000, toepoch=2000)

    async def test_client_error_raises_http_error(self):
        """aiohttp.ClientError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.urls["base"] = ""
        sensor = {"type": "motionsensor", "id": "sensor-003"}
        api.websession.request.side_effect = aiohttp.ClientError()
        with pytest.raises(web_exceptions.HTTPError):
            await api.motion_sensor(sensor, fromepoch=1000, toepoch=2000)


class TestGetWeather:
    """Cover lines 239-249: get_weather() success, space encoding, and error paths."""

    async def test_success_returns_status_and_parsed(self):
        """Successful call returns status and parsed weather JSON."""
        payload = {"temperature": {"value": 15, "unit": "C"}}
        api = _make_api(status=200, json_data=payload)
        result = await api.get_weather("?lat=51.5&lon=-0.1")
        assert result["original"] == 200
        assert result["parsed"] == payload

    async def test_space_in_weather_url_is_encoded(self):
        """Spaces in the weather_url are replaced with %20."""
        api = _make_api(status=200, json_data={})
        captured_url = []
        original_request = api.request

        async def capture_request(method, url, **kwargs):
            captured_url.append(url)
            return await original_request(method, url, **kwargs)

        with patch.object(api, "request", side_effect=capture_request):
            await api.get_weather("?postcode=SW1A 2AA")
        assert len(captured_url) == 1
        assert " " not in captured_url[0]
        assert "%20" in captured_url[0]

    async def test_url_is_prefixed_with_weather_base(self):
        """The weather base URL is prepended to the given weather_url."""
        api = _make_api(status=200, json_data={})
        captured_url = []
        original_request = api.request

        async def capture_request(method, url, **kwargs):
            captured_url.append(url)
            return await original_request(method, url, **kwargs)

        with patch.object(api, "request", side_effect=capture_request):
            await api.get_weather("?lat=51.5")
        assert captured_url[0].startswith("https://weather.prod.bgchprod.info/weather")

    async def test_os_error_raises_http_error(self):
        """OSError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.websession.request.side_effect = OSError("network fail")
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_weather("?lat=51.5")

    async def test_runtime_error_raises_http_error(self):
        """RuntimeError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.websession.request.side_effect = RuntimeError("unexpected")
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_weather("?lat=51.5")

    async def test_client_error_raises_http_error(self):
        """aiohttp.ClientError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.websession.request.side_effect = aiohttp.ClientError()
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_weather("?lat=51.5")

    async def test_connection_error_raises_http_error(self):
        """ConnectionError inside the try block causes error() → HTTPError."""
        api = _make_api(status=200)
        api.websession.request.side_effect = ConnectionError("disconnected")
        with pytest.raises(web_exceptions.HTTPError):
            await api.get_weather("?lat=51.5")


class TestSetStateJsonEncoding:
    """set_state must produce valid JSON even when kwarg values contain special characters."""

    async def test_set_state_escapes_quotes_in_value(self):
        """A value containing double-quotes must produce valid, parseable JSON."""
        session = MagicMock()
        session.tokens.token_data = {"token": "tok"}
        session.config.file = False
        api = HiveApiAsync(hive_session=session)
        api.urls = {"nodes": "https://beekeeper.hivehome.com/1.0/nodes/{}/{}"}

        captured = {}

        async def fake_request(_method, _url, **kwargs):
            captured["data"] = kwargs.get("data")
            resp = MagicMock()
            resp.status = 200
            resp.json = AsyncMock(return_value={})
            return resp

        with patch.object(api, "request", side_effect=fake_request):
            with patch.object(api, "is_file_being_used", new=AsyncMock()):
                await api.set_state("heating", "node-1", mode='MANUAL"injected')

        parsed = json.loads(captured["data"])
        assert parsed["mode"] == 'MANUAL"injected'
