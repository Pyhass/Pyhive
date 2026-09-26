"""Unit tests for HiveApi (sync)."""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from apyhiveapi.api.hive_api import HiveApi
from apyhiveapi.helper.hive_exceptions import HiveConnectionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(status_code=200, json_data=None, text=None):
    """Return a MagicMock that mimics a requests.Response."""
    if json_data is None:
        json_data = {"data": "test"}
    if text is None:
        text = json.dumps(json_data)
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = text
    return resp


def _make_api(session=None, token=None):
    """Return a HiveApi instance wired to a mock session."""
    if session is None:
        session = MagicMock()
        session.tokens = MagicMock()
        session.tokens.token_data = {"token": "test-token"}
        session.update_tokens = MagicMock()
    return HiveApi(hive_session=session, token=token)


def _make_api_no_session(token="bare-token"):
    """Return a HiveApi instance with no hive_session (uses self.token)."""
    return HiveApi(hive_session=None, token=token)


# ---------------------------------------------------------------------------
# Tests: HiveApi.__init__
# ---------------------------------------------------------------------------


class TestInit:
    def test_urls_contains_base(self):
        api = _make_api()
        assert "base" in api.urls
        assert "beekeeper-uk.hivehome.com" in api.urls["base"]

    def test_default_timeout(self):
        api = _make_api()
        assert api.timeout == 5

    def test_default_json_return_is_no_response(self):
        api = _make_api()
        assert "No response" in api.json_return["original"]

    def test_session_stored(self):
        session = MagicMock()
        api = HiveApi(hive_session=session)
        assert api.session is session

    def test_token_stored_when_no_session(self):
        api = HiveApi(hive_session=None, token="mytoken")
        assert api.token == "mytoken"

    def test_authorization_header_starts_empty(self):
        api = _make_api()
        assert api.headers["authorization"] == ""


# ---------------------------------------------------------------------------
# Tests: HiveApi.request
# ---------------------------------------------------------------------------


class TestRequest:
    def test_get_with_session_uses_session_token(self):
        """When a session is present the session token is used as authorization."""
        session = MagicMock()
        session.tokens = MagicMock()
        session.tokens.token_data = {"token": "session-tok"}
        api = HiveApi(hive_session=session)

        with patch("apyhiveapi.api.hive_api.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200)
            api.request("GET", "https://example.com/")
            _, call_kwargs = mock_get.call_args
            assert call_kwargs["headers"]["authorization"] == "session-tok"

    def test_get_without_session_uses_token(self):
        """When no session is present self.token is used as authorization."""
        api = _make_api_no_session(token="bare-tok")

        with patch("apyhiveapi.api.hive_api.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200)
            api.request("GET", "https://example.com/")
            _, call_kwargs = mock_get.call_args
            assert call_kwargs["headers"]["authorization"] == "bare-tok"

    def test_get_method_calls_requests_get(self):
        api = _make_api()
        with patch("apyhiveapi.api.hive_api.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200)
            api.request("GET", "https://example.com/")
            mock_get.assert_called_once()

    def test_post_method_calls_requests_post(self):
        api = _make_api()
        with patch("apyhiveapi.api.hive_api.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200)
            api.request("POST", "https://example.com/", jsc='{"key": "val"}')
            mock_post.assert_called_once()

    def test_unsupported_method_raises_value_error(self):
        api = _make_api()
        with pytest.raises(ValueError, match="Unsupported request type"):
            api.request("DELETE", "https://example.com/")

    def test_exception_is_reraised(self):
        api = _make_api()
        with patch(
            "apyhiveapi.api.hive_api.requests.get", side_effect=OSError("network down")
        ):
            with pytest.raises(OSError):
                api.request("GET", "https://example.com/")

    def test_request_passes_jsc_as_data(self):
        api = _make_api()
        payload = '{"foo": "bar"}'
        with patch("apyhiveapi.api.hive_api.requests.post") as mock_post:
            mock_post.return_value = _make_mock_response(200)
            api.request("POST", "https://example.com/", jsc=payload)
            _, call_kwargs = mock_post.call_args
            assert call_kwargs["data"] == payload

    def test_request_passes_timeout(self):
        api = _make_api()
        with patch("apyhiveapi.api.hive_api.requests.get") as mock_get:
            mock_get.return_value = _make_mock_response(200)
            api.request("GET", "https://example.com/")
            _, call_kwargs = mock_get.call_args
            assert call_kwargs["timeout"] == api.timeout


# ---------------------------------------------------------------------------
# Tests: HiveApi.get_login_info
# ---------------------------------------------------------------------------


class TestGetLoginInfo:
    def test_tls_verification_is_not_disabled(self):
        """The SSO bootstrap request must not pass verify=False."""
        api = _make_api()
        html_content = (
            b"<script>"
            b'window.HiveSSOPoolId="eu-west-1_abc",'
            b'window.HiveSSOPublicCognitoClientId="client123"'
            b"</script>"
        )
        mock_resp = MagicMock()
        mock_resp.content = html_content
        mock_resp.status_code = 200

        with patch(
            "apyhiveapi.api.hive_api.requests.get", return_value=mock_resp
        ) as mock_get:
            api.get_login_info()

        _, call_kwargs = mock_get.call_args
        assert call_kwargs.get("verify", True) is not False

    def test_successful_parse_returns_login_data(self):
        """Parses HiveSSOPoolId and HiveSSOPublicCognitoClientId from the SSO page."""
        api = _make_api()
        # The actual page embeds values in a <script> block as comma-separated
        # window.<key>=<value> assignments.
        html_content = (
            b"<script>"
            b'window.HiveSSOPoolId="eu-west-1_abc",'
            b'window.HiveSSOPublicCognitoClientId="client123"'
            b"</script>"
        )
        mock_resp = MagicMock()
        mock_resp.content = html_content
        mock_resp.status_code = 200

        with patch("apyhiveapi.api.hive_api.requests.get", return_value=mock_resp):
            result = api.get_login_info()

        assert result is not None
        assert result["UPID"] == "eu-west-1_abc"
        assert result["CLIID"] == "client123"
        # REGION mirrors UPID
        assert result["REGION"] == "eu-west-1_abc"

    def test_os_error_calls_error_and_raises_connection_error(self):
        api = _make_api()
        with (
            patch(
                "apyhiveapi.api.hive_api.requests.get",
                side_effect=OSError("net error"),
            ),
            pytest.raises(HiveConnectionError),
        ):
            api.get_login_info()

        assert api.json_return["original"] == "Error making API call"

    def test_timeout_raises_connection_error(self):
        """A read timeout on the SSO page is transient, so it must not return None."""
        api = _make_api()
        with (
            patch(
                "apyhiveapi.api.hive_api.requests.get",
                side_effect=requests.exceptions.ReadTimeout("read timed out"),
            ),
            pytest.raises(HiveConnectionError),
        ):
            api.get_login_info()

    def test_runtime_error_calls_error_and_returns_none(self):
        api = _make_api()
        with patch(
            "apyhiveapi.api.hive_api.requests.get",
            side_effect=RuntimeError("boom"),
        ):
            result = api.get_login_info()

        assert result is None
        assert api.json_return["original"] == "Error making API call"

    def test_key_error_calls_error_and_returns_none(self):
        """If the script block is missing expected keys, KeyError triggers error()."""
        api = _make_api()
        # HTML with no relevant keys — PyQuery will find the script but
        # json parsing will succeed with an empty dict, then KeyError on lookup.
        html_content = b"<script>window.SomeOtherKey=value</script>"
        mock_resp = MagicMock()
        mock_resp.content = html_content
        mock_resp.status_code = 200

        with patch("apyhiveapi.api.hive_api.requests.get", return_value=mock_resp):
            result = api.get_login_info()

        assert result is None


# ---------------------------------------------------------------------------
# Tests: HiveApi.get_all
# ---------------------------------------------------------------------------


class TestGetAll:
    def test_successful_returns_original_and_parsed(self):
        api = _make_api()
        payload = {"products": [], "devices": []}
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.get_all()

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_none_response_logs_error_and_returns_no_response_marker(self):
        """When request returns None the method should not crash."""
        api = _make_api()
        with patch.object(api, "request", return_value=None):
            result = api.get_all()

        assert result["original"] == "No response to Hive API request"

    def test_os_error_calls_error_method(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError("net error")):
            api.get_all()

        assert api.json_return["original"] == "Error making API call"

    def test_runtime_error_calls_error_method(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=RuntimeError("boom")):
            api.get_all()

        assert api.json_return["original"] == "Error making API call"


# ---------------------------------------------------------------------------
# Tests: HiveApi.get_devices / get_products / get_actions
# ---------------------------------------------------------------------------


class TestGetDevices:
    def test_success(self):
        api = _make_api()
        payload = [{"id": "dev1"}]
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.get_devices()

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_os_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError("net error")):
            api.get_devices()

        assert api.json_return["original"] == "Error making API call"

    def test_runtime_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=RuntimeError("boom")):
            api.get_devices()

        assert api.json_return["original"] == "Error making API call"

    def test_url_contains_devices_path(self):
        """The URL passed to request must include the /devices path segment."""
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data=[])

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.get_devices()
            url_arg = mock_req.call_args[0][1]
            assert "/devices" in url_arg


class TestGetProducts:
    def test_success(self):
        api = _make_api()
        payload = [{"id": "prod1"}]
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.get_products()

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_os_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError):
            api.get_products()

        assert api.json_return["original"] == "Error making API call"

    def test_url_contains_products_path(self):
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data=[])

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.get_products()
            url_arg = mock_req.call_args[0][1]
            assert "/products" in url_arg


class TestGetActions:
    def test_success(self):
        api = _make_api()
        payload = [{"id": "act1"}]
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.get_actions()

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_os_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError):
            api.get_actions()

        assert api.json_return["original"] == "Error making API call"

    def test_url_contains_actions_path(self):
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data=[])

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.get_actions()
            url_arg = mock_req.call_args[0][1]
            assert "/actions" in url_arg


# ---------------------------------------------------------------------------
# Tests: HiveApi.motion_sensor
# ---------------------------------------------------------------------------


class TestMotionSensor:
    def test_builds_url_and_returns_data(self):
        api = _make_api()
        sensor = {"type": "motionsensor", "id": "sensor-abc"}
        payload = [{"event": "motion"}]
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            result = api.motion_sensor(sensor, 1000, 2000)

        assert result["original"] == 200
        assert result["parsed"] == payload
        url_arg = mock_req.call_args[0][1]
        assert "motionsensor" in url_arg
        assert "sensor-abc" in url_arg
        assert "from=1000" in url_arg
        assert "to=2000" in url_arg

    def test_os_error_calls_error(self):
        api = _make_api()
        sensor = {"type": "motionsensor", "id": "s1"}
        with patch.object(api, "request", side_effect=OSError):
            api.motion_sensor(sensor, 0, 100)

        assert api.json_return["original"] == "Error making API call"

    def test_runtime_error_calls_error(self):
        api = _make_api()
        sensor = {"type": "motionsensor", "id": "s1"}
        with patch.object(api, "request", side_effect=RuntimeError("fail")):
            api.motion_sensor(sensor, 0, 100)

        assert api.json_return["original"] == "Error making API call"


# ---------------------------------------------------------------------------
# Tests: HiveApi.get_weather
# ---------------------------------------------------------------------------


class TestGetWeather:
    def test_success(self):
        api = _make_api()
        payload = {"temperature": {"value": 15}}
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.get_weather("?postcode=EC1A1BB")

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_encodes_spaces_in_url(self):
        """Spaces in the weather_url parameter must be percent-encoded."""
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={"temp": 10})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.get_weather("?location=London EC1")

        url_arg = mock_req.call_args[0][1]
        assert " " not in url_arg
        assert "%20" in url_arg

    def test_weather_base_url_prepended(self):
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.get_weather("?postcode=SW1A1AA")

        url_arg = mock_req.call_args[0][1]
        assert "weather.prod.bgchprod.info" in url_arg

    def test_os_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError):
            api.get_weather("?postcode=EC1A1BB")

        assert api.json_return["original"] == "Error making API call"

    def test_connection_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=ConnectionError):
            api.get_weather("?postcode=EC1A1BB")

        assert api.json_return["original"] == "Error making API call"


# ---------------------------------------------------------------------------
# Tests: HiveApi.set_state
# ---------------------------------------------------------------------------


class TestSetState:
    def test_success_returns_status_and_parsed(self):
        api = _make_api()
        payload = {"id": "node-1", "mode": "MANUAL"}
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.set_state("heating", "node-1", mode="MANUAL")

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_none_response_logs_error_no_crash(self):
        """When request returns None the method must not raise."""
        api = _make_api()
        with patch.object(api, "request", return_value=None):
            result = api.set_state("heating", "node-1", mode="MANUAL")

        assert result["original"] == "No response to Hive API request"

    def test_os_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError("fail")):
            api.set_state("heating", "node-1", mode="MANUAL")

        assert api.json_return["original"] == "Error making API call"

    def test_runtime_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=RuntimeError("boom")):
            api.set_state("heating", "node-1")

        assert api.json_return["original"] == "Error making API call"

    def test_url_contains_node_type_and_id(self):
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.set_state("hotwater", "hw-node-99", status="ON")

        url_arg = mock_req.call_args[0][1]
        assert "hotwater" in url_arg
        assert "hw-node-99" in url_arg

    def test_kwargs_serialised_into_jsc(self):
        """Keyword arguments must appear in the JSON payload sent to request."""
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.set_state("heating", "n1", mode="SCHEDULE", target=21)

        jsc_arg = mock_req.call_args[0][2]
        assert "mode" in jsc_arg
        assert "SCHEDULE" in jsc_arg
        assert "target" in jsc_arg
        assert "21" in jsc_arg

    def test_payload_is_valid_json_with_native_types(self):
        """The payload must round-trip through json.loads with types intact."""
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.set_state("heating", "n1", mode="SCHEDULE", target=21.5)

        jsc_arg = mock_req.call_args[0][2]
        assert json.loads(jsc_arg) == {"mode": "SCHEDULE", "target": 21.5}

    def test_payload_with_quotes_is_valid_json(self):
        """Values containing quotes must not break or inject into the JSON."""
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.set_state("heating", "n1", name='say "hi", "extra": "injected')

        jsc_arg = mock_req.call_args[0][2]
        assert json.loads(jsc_arg) == {"name": 'say "hi", "extra": "injected'}


# ---------------------------------------------------------------------------
# Tests: HiveApi.set_action
# ---------------------------------------------------------------------------


class TestSetAction:
    def test_success(self):
        api = _make_api()
        payload = {"id": "act-1", "status": "ACTIVE"}
        mock_resp = _make_mock_response(200, json_data=payload)

        with patch.object(api, "request", return_value=mock_resp):
            result = api.set_action("act-1", '{"status": "ACTIVE"}')

        assert result["original"] == 200
        assert result["parsed"] == payload

    def test_url_contains_action_id(self):
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.set_action("my-action-id", "{}")

        url_arg = mock_req.call_args[0][1]
        assert "my-action-id" in url_arg

    def test_data_passed_as_jsc(self):
        api = _make_api()
        mock_resp = _make_mock_response(200, json_data={})
        action_data = '{"enabled": true}'

        with patch.object(api, "request", return_value=mock_resp) as mock_req:
            api.set_action("act-2", action_data)

        jsc_arg = mock_req.call_args[0][2]
        assert jsc_arg == action_data

    def test_os_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=OSError):
            api.set_action("act-1", "{}")

        assert api.json_return["original"] == "Error making API call"

    def test_connection_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=ConnectionError):
            api.set_action("act-1", "{}")

        assert api.json_return["original"] == "Error making API call"

    def test_runtime_error_calls_error(self):
        api = _make_api()
        with patch.object(api, "request", side_effect=RuntimeError("fail")):
            api.set_action("act-1", "{}")

        assert api.json_return["original"] == "Error making API call"


# ---------------------------------------------------------------------------
# Tests: result isolation between calls
# ---------------------------------------------------------------------------


class TestResultIsolation:
    def test_results_are_independent_between_calls(self):
        """A later call must not mutate the dict returned by an earlier call."""
        api = _make_api()
        resp_devices = _make_mock_response(200, json_data=[{"id": "dev1"}])
        resp_products = _make_mock_response(200, json_data=[{"id": "prod1"}])

        with patch.object(api, "request", side_effect=[resp_devices, resp_products]):
            devices = api.get_devices()
            products = api.get_products()

        assert devices is not products
        assert devices["parsed"] == [{"id": "dev1"}]
        assert products["parsed"] == [{"id": "prod1"}]

    def test_error_call_does_not_corrupt_previous_result(self):
        """An error in a later call must not overwrite an earlier result."""
        api = _make_api()
        resp_devices = _make_mock_response(200, json_data=[{"id": "dev1"}])

        with patch.object(api, "request", side_effect=[resp_devices, OSError("down")]):
            devices = api.get_devices()
            failed = api.get_products()

        assert devices["original"] == 200
        assert devices["parsed"] == [{"id": "dev1"}]
        assert failed["original"] == "Error making API call"

    def test_set_state_none_response_does_not_return_stale_data(self):
        """set_state with no response must not surface a previous call's payload."""
        api = _make_api()
        resp_devices = _make_mock_response(200, json_data=[{"id": "dev1"}])

        with patch.object(api, "request", side_effect=[resp_devices, None]):
            api.get_devices()
            result = api.set_state("heating", "n1", mode="MANUAL")

        assert result["parsed"] != [{"id": "dev1"}]
        assert result["original"] == "No response to Hive API request"


# ---------------------------------------------------------------------------
# Tests: HiveApi.error
# ---------------------------------------------------------------------------


class TestError:
    def test_error_updates_json_return_original(self):
        api = _make_api()
        api.error()
        assert api.json_return["original"] == "Error making API call"

    def test_error_updates_json_return_parsed(self):
        api = _make_api()
        api.error()
        assert api.json_return["parsed"] == "Error making API call"

    def test_error_does_not_raise(self):
        """error() must be side-effect only — no exception raised."""
        api = _make_api()
        api.error()  # must not raise

    def test_error_overwrites_previous_json_return(self):
        api = _make_api()
        api.json_return["original"] = 200
        api.json_return["parsed"] = {"some": "data"}
        api.error()
        assert api.json_return["original"] == "Error making API call"
        assert api.json_return["parsed"] == "Error making API call"
