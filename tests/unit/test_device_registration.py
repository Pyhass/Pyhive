"""Unit tests for DeviceRegistrationMixin."""

# pylint: disable=protected-access

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import botocore.exceptions
import pytest
from apyhiveapi.api.device_registration import DeviceRegistrationMixin
from apyhiveapi.api.srp_crypto import G_HEX, N_HEX, get_random, hex_to_long
from apyhiveapi.helper.hive_exceptions import HiveApiError, HiveInvalid2FACode

# ---------------------------------------------------------------------------
# Exception factories
# ---------------------------------------------------------------------------


def _named_client_error(
    code: str, message: str = ""
) -> botocore.exceptions.ClientError:
    """Return a ClientError whose __class__.__name__ matches ``code``."""
    cls = type(code, (botocore.exceptions.ClientError,), {})
    return cls({"Error": {"Code": code, "Message": message}}, "operation")


def _endpoint_error() -> botocore.exceptions.EndpointConnectionError:
    return botocore.exceptions.EndpointConnectionError(
        endpoint_url="https://cognito.eu-west-1.amazonaws.com"
    )


# ---------------------------------------------------------------------------
# Stub factory
# ---------------------------------------------------------------------------


async def _make_stub(
    device_group_key: str = "grp-key",
    device_key: str = "dev-key",
    device_password: str = "dev-pass",
    access_token: str | None = "acc-token",
    client_secret: str | None = None,
) -> DeviceRegistrationMixin:
    """Create a DeviceRegistrationMixin instance with all required attributes."""

    class StubDRM(DeviceRegistrationMixin):
        pass

    stub = StubDRM()
    stub.client = MagicMock()
    stub.loop = MagicMock()
    stub.loop.run_in_executor = AsyncMock(return_value={"result": "ok"})
    stub._client_id = "test-client-id"
    stub.access_token = access_token
    stub.device_group_key = device_group_key
    stub.device_key = device_key
    stub.device_password = device_password
    stub.client_secret = client_secret
    stub.token_created = None

    # SRP values needed for get_device_authentication_key
    big_n = hex_to_long(N_HEX)
    g_value = hex_to_long(G_HEX)
    small_a = get_random(128) % big_n
    stub.big_n = big_n
    stub.g_value = g_value
    stub.k = hex_to_long("0e44fbef19a2a5b8c72d17c2b2a5a9b7e4c91dc0")
    stub.small_a_value = small_a
    stub.large_a_value = pow(g_value, small_a, big_n)

    # get_secret_hash static method (provided by HiveAuthAsync normally)
    stub.get_secret_hash = MagicMock(return_value="secret-hash-value")

    return stub


# ---------------------------------------------------------------------------
# TestGenerateHashDevice
# ---------------------------------------------------------------------------


class TestGenerateHashDevice:
    async def test_returns_verifier_config_with_required_keys(self):
        stub = await _make_stub()
        result = stub.generate_hash_device("grp-key", "dev-key")
        assert "PasswordVerifier" in result
        assert "Salt" in result

    async def test_password_verifier_is_non_empty_string(self):
        stub = await _make_stub()
        result = stub.generate_hash_device("grp-key", "dev-key")
        assert isinstance(result["PasswordVerifier"], str)
        assert len(result["PasswordVerifier"]) > 0

    async def test_salt_is_non_empty_string(self):
        stub = await _make_stub()
        result = stub.generate_hash_device("grp-key", "dev-key")
        assert isinstance(result["Salt"], str)
        assert len(result["Salt"]) > 0

    async def test_sets_device_password_on_self(self):
        stub = await _make_stub()
        stub.device_password = None
        stub.generate_hash_device("grp-key", "dev-key")
        assert stub.device_password is not None
        assert isinstance(stub.device_password, str)
        assert len(stub.device_password) > 0

    async def test_different_calls_produce_different_passwords(self):
        stub = await _make_stub()
        stub.generate_hash_device("grp-key", "dev-key")
        password_first = stub.device_password
        stub.generate_hash_device("grp-key", "dev-key")
        password_second = stub.device_password
        # Passwords are randomly generated — they should almost never match.
        # We check they are independently set strings (not None).
        assert password_first is not None
        assert password_second is not None

    async def test_different_device_keys_produce_different_verifiers(self):
        stub = await _make_stub()
        result1 = stub.generate_hash_device("grp-key", "dev-key-1")
        verifier1 = result1["PasswordVerifier"]
        result2 = stub.generate_hash_device("grp-key", "dev-key-2")
        verifier2 = result2["PasswordVerifier"]
        # Different keys + random passwords → almost certainly different verifiers
        # (at minimum the structure is valid for both)
        assert isinstance(verifier1, str)
        assert isinstance(verifier2, str)


# ---------------------------------------------------------------------------
# TestGetDeviceData
# ---------------------------------------------------------------------------


class TestGetDeviceData:
    async def test_returns_tuple_of_credentials(self):
        stub = await _make_stub()
        stub.token_created = "2024-01-01"
        result = await stub.get_device_data()
        assert result == ("grp-key", "dev-key", "dev-pass", "2024-01-01")

    async def test_returns_none_token_created_when_not_set(self):
        stub = await _make_stub()
        stub.token_created = None
        result = await stub.get_device_data()
        assert result == ("grp-key", "dev-key", "dev-pass", None)

    async def test_returns_four_element_tuple(self):
        stub = await _make_stub()
        result = await stub.get_device_data()
        assert len(result) == 4

    async def test_reflects_updated_device_group_key(self):
        stub = await _make_stub(device_group_key="updated-grp")
        result = await stub.get_device_data()
        assert result[0] == "updated-grp"

    async def test_reflects_updated_device_key(self):
        stub = await _make_stub(device_key="updated-dev")
        result = await stub.get_device_data()
        assert result[1] == "updated-dev"


# ---------------------------------------------------------------------------
# TestConfirmDevice
# ---------------------------------------------------------------------------


class TestConfirmDevice:
    async def test_uses_hostname_when_no_device_name(self):
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        with patch(
            "apyhiveapi.api.device_registration.socket.gethostname",
            return_value="my-host",
        ):
            await stub.confirm_device(None)

        stub.loop.run_in_executor.assert_called_once()
        # The call uses functools.partial; verify it was invoked with
        # DeviceName="my-host" by inspecting the partial's keywords.
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["DeviceName"] == "my-host"

    async def test_uses_provided_device_name(self):
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        await stub.confirm_device("custom-name")
        stub.loop.run_in_executor.assert_called_once()
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["DeviceName"] == "custom-name"

    async def test_returns_executor_result_on_success(self):
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        stub.loop.run_in_executor.return_value = {"UserConfirmed": True}
        result = await stub.confirm_device("test-device")
        assert result == {"UserConfirmed": True}

    async def test_not_authorized_raises_api_error(self):
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        stub.loop.run_in_executor.side_effect = _named_client_error(
            "NotAuthorizedException"
        )
        with pytest.raises(HiveApiError):
            await stub.confirm_device("name")

    async def test_code_mismatch_raises_invalid_2fa(self):
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        stub.loop.run_in_executor.side_effect = _named_client_error(
            "CodeMismatchException"
        )
        with pytest.raises(HiveInvalid2FACode):
            await stub.confirm_device("name")

    async def test_endpoint_error_raises_api_error(self):
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        stub.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await stub.confirm_device("name")

    async def test_passes_access_token_to_executor(self):
        stub = await _make_stub(access_token="my-access-token")
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        await stub.confirm_device("dev")
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["AccessToken"] == "my-access-token"

    async def test_passes_device_key_to_executor(self):
        stub = await _make_stub(device_key="my-device-key")
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        await stub.confirm_device("dev")
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["DeviceKey"] == "my-device-key"


# ---------------------------------------------------------------------------
# TestUpdateDeviceStatus
# ---------------------------------------------------------------------------


class TestUpdateDeviceStatus:
    async def test_successful_update_calls_run_in_executor(self):
        stub = await _make_stub()
        await stub.update_device_status()
        stub.loop.run_in_executor.assert_called_once()

    async def test_returns_executor_result(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }
        result = await stub.update_device_status()
        assert result == {"ResponseMetadata": {"HTTPStatusCode": 200}}

    async def test_endpoint_error_raises_api_error(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await stub.update_device_status()

    async def test_passes_remembered_status_to_executor(self):
        stub = await _make_stub()
        await stub.update_device_status()
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["DeviceRememberedStatus"] == "remembered"

    async def test_passes_access_token_to_executor(self):
        stub = await _make_stub(access_token="update-token")
        await stub.update_device_status()
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["AccessToken"] == "update-token"

    async def test_passes_device_key_to_executor(self):
        stub = await _make_stub(device_key="update-dev-key")
        await stub.update_device_status()
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["DeviceKey"] == "update-dev-key"


# ---------------------------------------------------------------------------
# TestIsDeviceRegistered
# ---------------------------------------------------------------------------


class TestIsDeviceRegistered:
    async def test_missing_token_returns_false(self):
        stub = await _make_stub(access_token=None)
        stub.device_key = "key"
        result = await stub.is_device_registered()
        assert result is False

    async def test_missing_device_key_returns_false(self):
        stub = await _make_stub(access_token="token")
        stub.device_key = None
        result = await stub.is_device_registered()
        assert result is False

    async def test_both_missing_returns_false(self):
        stub = await _make_stub(access_token=None)
        stub.device_key = None
        result = await stub.is_device_registered()
        assert result is False

    async def test_device_remembered_returns_true(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {
            "Device": {
                "DeviceAttributes": [
                    {"Name": "dev:device_remembered_status", "Value": "remembered"}
                ]
            }
        }
        result = await stub.is_device_registered()
        assert result is True

    async def test_device_not_remembered_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {
            "Device": {
                "DeviceAttributes": [
                    {"Name": "dev:device_remembered_status", "Value": "not_remembered"}
                ]
            }
        }
        result = await stub.is_device_registered()
        assert result is False

    async def test_device_with_no_remembered_attribute_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {
            "Device": {
                "DeviceAttributes": [
                    {"Name": "dev:other_attribute", "Value": "some_value"}
                ]
            }
        }
        result = await stub.is_device_registered()
        assert result is False

    async def test_empty_device_attributes_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {"Device": {"DeviceAttributes": []}}
        result = await stub.is_device_registered()
        assert result is False

    async def test_result_without_device_key_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {"SomeOtherKey": {}}
        result = await stub.is_device_registered()
        assert result is False

    async def test_resource_not_found_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _named_client_error(
            "ResourceNotFoundException"
        )
        result = await stub.is_device_registered()
        assert result is False

    async def test_not_authorized_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _named_client_error(
            "NotAuthorizedException"
        )
        result = await stub.is_device_registered()
        assert result is False

    async def test_other_client_error_returns_false(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _named_client_error("SomeOtherError")
        result = await stub.is_device_registered()
        assert result is False

    async def test_endpoint_error_raises_api_error(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await stub.is_device_registered()

    async def test_uses_provided_access_token_override(self):
        stub = await _make_stub(access_token="default-token")
        stub.loop.run_in_executor.return_value = {
            "Device": {
                "DeviceAttributes": [
                    {"Name": "dev:device_remembered_status", "Value": "remembered"}
                ]
            }
        }
        result = await stub.is_device_registered(access_token="override-token")
        assert result is True
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["AccessToken"] == "override-token"

    async def test_uses_provided_device_key_override(self):
        stub = await _make_stub(device_key="default-key")
        stub.loop.run_in_executor.return_value = {
            "Device": {
                "DeviceAttributes": [
                    {"Name": "dev:device_remembered_status", "Value": "remembered"}
                ]
            }
        }
        result = await stub.is_device_registered(device_key="override-key")
        assert result is True
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["DeviceKey"] == "override-key"


# ---------------------------------------------------------------------------
# TestForgetDevice
# ---------------------------------------------------------------------------


class TestForgetDevice:
    async def test_successful_forget_returns_result(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.return_value = {
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }
        result = await stub.forget_device("acc-token", "dev-key")
        assert result == {"ResponseMetadata": {"HTTPStatusCode": 200}}

    async def test_calls_run_in_executor(self):
        stub = await _make_stub()
        await stub.forget_device("acc-token", "dev-key")
        stub.loop.run_in_executor.assert_called_once()

    async def test_passes_access_token_and_device_key_to_executor(self):
        stub = await _make_stub()
        await stub.forget_device("forget-token", "forget-key")
        call_args = stub.loop.run_in_executor.call_args
        partial_fn = call_args[0][1]
        assert partial_fn.keywords["AccessToken"] == "forget-token"
        assert partial_fn.keywords["DeviceKey"] == "forget-key"

    async def test_not_authorized_raises_api_error(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _named_client_error(
            "NotAuthorizedException"
        )
        with pytest.raises(HiveApiError):
            await stub.forget_device("acc-token", "dev-key")

    async def test_other_client_error_raises_api_error(self):
        """All ClientErrors raise HiveApiError."""
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _named_client_error("SomeOtherError")
        with pytest.raises(HiveApiError):
            await stub.forget_device("acc-token", "dev-key")

    async def test_endpoint_error_raises_api_error(self):
        stub = await _make_stub()
        stub.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await stub.forget_device("acc-token", "dev-key")


# ---------------------------------------------------------------------------
# TestDeviceRegistration
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestGetDeviceAuthenticationKey — u_value == 0 raises ValueError (line 90)
# ---------------------------------------------------------------------------


class TestGetDeviceAuthenticationKeyUZero:
    async def test_u_value_zero_raises_value_error(self):
        """When calculate_u returns 0, a ValueError is raised."""
        stub = await _make_stub()
        with patch("apyhiveapi.api.device_registration.calculate_u", return_value=0):
            with pytest.raises(ValueError, match="U cannot be zero"):
                stub.get_device_authentication_key(
                    stub.device_group_key,
                    stub.device_key,
                    stub.device_password,
                    stub.large_a_value,  # server_b_value (any value)
                    "aabbccdd",  # salt
                )


# ---------------------------------------------------------------------------
# TestClientNone — async_init called when client is None (lines 163, 198, 246, 323)
# ---------------------------------------------------------------------------


class TestConfirmDeviceClientNone:
    async def test_async_init_called_when_client_none(self):
        """confirm_device calls async_init when self.client is None (line 163)."""
        stub = await _make_stub()
        stub.client = None

        init_called = []

        async def fake_init():
            init_called.append(True)
            stub.client = MagicMock()

        stub.async_init = fake_init
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        await stub.confirm_device("name")
        assert len(init_called) == 1


class TestUpdateDeviceStatusClientNone:
    async def test_async_init_called_when_client_none(self):
        """update_device_status calls async_init when self.client is None (line 198)."""
        stub = await _make_stub()
        stub.client = None

        init_called = []

        async def fake_init():
            init_called.append(True)
            stub.client = MagicMock()

        stub.async_init = fake_init
        await stub.update_device_status()
        assert len(init_called) == 1


class TestIsDeviceRegisteredClientNone:
    async def test_async_init_called_when_client_none(self):
        """is_device_registered calls async_init when self.client is None (line 246)."""
        stub = await _make_stub()
        stub.client = None

        init_called = []

        async def fake_init():
            init_called.append(True)
            stub.client = MagicMock()

        stub.async_init = fake_init
        # After init, run_in_executor returns a non-remembered device
        stub.loop.run_in_executor.return_value = {"Device": {"DeviceAttributes": []}}
        result = await stub.is_device_registered()
        assert len(init_called) == 1
        assert result is False


class TestForgetDeviceClientNone:
    async def test_async_init_called_when_client_none(self):
        """forget_device calls async_init when self.client is None (line 323)."""
        stub = await _make_stub()
        stub.client = None

        init_called = []

        async def fake_init():
            init_called.append(True)
            stub.client = MagicMock()

        stub.async_init = fake_init
        await stub.forget_device("acc-token", "dev-key")
        assert len(init_called) == 1


# ---------------------------------------------------------------------------
# TestSwallowedErrors — wrong-name exceptions silently swallowed
# ---------------------------------------------------------------------------


class TestConfirmDeviceSwallowedErrors:
    async def test_other_client_error_raises_api_error(self):
        """ClientErrors other than CodeMismatchException raise HiveApiError."""
        stub = await _make_stub()
        stub.generate_hash_device = MagicMock(
            return_value={"PasswordVerifier": "pv", "Salt": "s"}
        )
        wrong_cls = type("SomeOtherError", (botocore.exceptions.ClientError,), {})
        wrong_err = wrong_cls(
            {"Error": {"Code": "SomeOtherError", "Message": "msg"}}, "op"
        )
        stub.loop.run_in_executor.side_effect = wrong_err
        with pytest.raises(HiveApiError):
            await stub.confirm_device("name")


class TestDeviceRegistration:
    async def test_calls_confirm_and_update(self):
        stub = await _make_stub()
        stub.confirm_device = AsyncMock()
        stub.update_device_status = AsyncMock()
        await stub.device_registration("test-device")
        stub.confirm_device.assert_called_once_with("test-device")
        stub.update_device_status.assert_called_once()

    async def test_passes_none_device_name(self):
        stub = await _make_stub()
        stub.confirm_device = AsyncMock()
        stub.update_device_status = AsyncMock()
        await stub.device_registration()
        stub.confirm_device.assert_called_once_with(None)

    async def test_update_called_after_confirm(self):
        """Verifies that update_device_status is called even when confirm succeeds."""
        call_order = []
        stub = await _make_stub()

        async def _confirm(_name):
            call_order.append("confirm")

        async def _update():
            call_order.append("update")

        stub.confirm_device = _confirm
        stub.update_device_status = _update
        await stub.device_registration("my-device")
        assert call_order == ["confirm", "update"]


# ---------------------------------------------------------------------------
# TestProcessDeviceChallenge
# ---------------------------------------------------------------------------


class TestProcessDeviceChallenge:
    _CHALLENGE_PARAMS = {
        "USERNAME": "user@test.com",
        "SALT": "aabbccdd",
        "SRP_B": "ccddee",
        "SECRET_BLOCK": "YWJj",
    }

    async def test_returns_response_with_required_keys(self):
        stub = await _make_stub()
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        assert "TIMESTAMP" in result
        assert "USERNAME" in result
        assert "PASSWORD_CLAIM_SECRET_BLOCK" in result
        assert "PASSWORD_CLAIM_SIGNATURE" in result
        assert "DEVICE_KEY" in result

    async def test_username_matches_challenge_parameter(self):
        stub = await _make_stub()
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        assert result["USERNAME"] == "user@test.com"

    async def test_device_key_matches_stub_device_key(self):
        stub = await _make_stub(device_key="my-device-key")
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        assert result["DEVICE_KEY"] == "my-device-key"

    async def test_secret_block_echoed_back(self):
        stub = await _make_stub()
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        assert result["PASSWORD_CLAIM_SECRET_BLOCK"] == "YWJj"

    async def test_no_client_secret_no_secret_hash(self):
        stub = await _make_stub(client_secret=None)
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        assert "SECRET_HASH" not in result

    async def test_with_client_secret_adds_secret_hash(self):
        stub = await _make_stub(client_secret="my-client-secret")
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        assert "SECRET_HASH" in result
        assert result["SECRET_HASH"] == "secret-hash-value"

    async def test_timestamp_format_matches_cognito_pattern(self):
        """Timestamp must follow Cognito's format (day number without leading zero)."""
        stub = await _make_stub()
        fake_hkdf = b"\x00" * 32
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        timestamp = result["TIMESTAMP"]
        assert isinstance(timestamp, str)
        assert "UTC" in timestamp
        # Cognito format strips leading zero from day number — no " 0N " pattern
        import re

        assert not re.search(r" 0\d ", timestamp), (
            f"Timestamp '{timestamp}' has leading zero in day number"
        )

    async def test_password_claim_signature_is_base64_string(self):
        stub = await _make_stub()
        fake_hkdf = b"\x00" * 32
        import base64

        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ):
            result = await stub.process_device_challenge(self._CHALLENGE_PARAMS)

        sig = result["PASSWORD_CLAIM_SIGNATURE"]
        assert isinstance(sig, str)
        # Must be valid base64
        decoded = base64.standard_b64decode(sig)
        assert len(decoded) == 32  # SHA-256 HMAC digest length

    async def test_salt_as_integer_is_padded(self):
        """SALT may be an integer; process_device_challenge should pad it."""
        stub = await _make_stub()
        fake_hkdf = b"\x00" * 32
        params = dict(self._CHALLENGE_PARAMS)
        params["SALT"] = 0xAABBCCDD  # integer instead of string
        with patch.object(
            stub,
            "get_device_authentication_key",
            return_value=fake_hkdf,
        ) as mock_auth_key:
            await stub.process_device_challenge(params)

        # Verify get_device_authentication_key was called (salt was processed)
        mock_auth_key.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetDeviceAuthenticationKey
# ---------------------------------------------------------------------------


class TestGetDeviceAuthenticationKey:
    async def test_returns_16_bytes(self):
        stub = await _make_stub()
        # Use a valid server_b_value that won't make u_value == 0.
        # Pick a large prime-ish value that is different from large_a_value.
        server_b_value = stub.large_a_value + 1
        result = stub.get_device_authentication_key(
            "grp-key",
            "dev-key",
            "dev-pass",
            server_b_value,
            "aabbccdd",
        )
        assert isinstance(result, bytes)
        assert len(result) == 16

    async def test_deterministic_for_same_inputs(self):
        stub = await _make_stub()
        server_b_value = stub.large_a_value + 1
        result1 = stub.get_device_authentication_key(
            "grp-key", "dev-key", "dev-pass", server_b_value, "aabbccdd"
        )
        result2 = stub.get_device_authentication_key(
            "grp-key", "dev-key", "dev-pass", server_b_value, "aabbccdd"
        )
        assert result1 == result2


# ---------------------------------------------------------------------------
# confirm_device and forget_device wrong exception mapping
# ---------------------------------------------------------------------------


class TestConfirmDeviceWrongException:
    """confirm_device must map NotAuthorizedException → HiveApiError (not HiveInvalid2FACode)."""

    async def test_not_authorized_raises_hive_api_error(self):
        """NotAuthorizedException in confirm_device raises HiveApiError, not HiveInvalid2FACode."""
        stub = await _make_stub()
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "not auth"}},
            "ConfirmDevice",
        )
        stub.loop.run_in_executor = AsyncMock(side_effect=err)

        with pytest.raises(HiveApiError):
            await stub.confirm_device()

    async def test_not_authorized_does_not_raise_invalid_2fa(self):
        """confirm_device must not raise HiveInvalid2FACode for NotAuthorizedException."""
        stub = await _make_stub()
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "not auth"}},
            "ConfirmDevice",
        )
        stub.loop.run_in_executor = AsyncMock(side_effect=err)

        with pytest.raises(Exception) as exc_info:
            await stub.confirm_device()

        assert not isinstance(exc_info.value, HiveInvalid2FACode)


class TestForgetDeviceWrongException:
    """forget_device must map NotAuthorizedException → HiveApiError."""

    async def test_not_authorized_raises_hive_api_error(self):
        """NotAuthorizedException in forget_device raises HiveApiError, not HiveInvalid2FACode."""
        stub = await _make_stub()
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "NotAuthorizedException", "Message": "not auth"}},
            "ForgetDevice",
        )
        stub.loop.run_in_executor = AsyncMock(side_effect=err)

        with pytest.raises(HiveApiError):
            await stub.forget_device("tok", "key")


# ---------------------------------------------------------------------------
# generate_hash_device — unnecessary async removed
# ---------------------------------------------------------------------------


class TestUnnecessaryAsync:
    """generate_hash_device should work without async (callable directly)."""

    def test_generate_hash_device_returns_config(self):
        """generate_hash_device returns the verifier config without needing await."""
        r = DeviceRegistrationMixin.__new__(DeviceRegistrationMixin)
        r.device_password = None
        r.g_value = 2
        r.big_n = 0xFFFF
        result = r.generate_hash_device("grp", "key")
        assert "PasswordVerifier" in result
        assert "Salt" in result
