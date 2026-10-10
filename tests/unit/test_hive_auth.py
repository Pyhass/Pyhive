"""Unit tests for the sync HiveAuth class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import botocore.exceptions
import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveApiError,
    HiveInvalid2FACode,
    HiveInvalidDeviceAuthentication,
    HiveInvalidPassword,
    HiveInvalidUsername,
    HiveReauthRequired,
)

# ---------------------------------------------------------------------------
# Constants / helpers
# ---------------------------------------------------------------------------

_LOGIN_INFO = {
    "UPID": "eu-west-1_TestPool",
    "CLIID": "test-client-id",
    "REGION": "eu-west-1_TestPool",
}


def _make_auth(
    username: str = "user@example.com",
    password: str = "pass",
    **kwargs,
):
    """Construct a HiveAuth instance with all network calls patched out."""
    from apyhiveapi.api.hive_auth import HiveAuth

    with (
        patch("apyhiveapi.api.hive_auth.HiveApi") as mock_api_cls,
        patch("apyhiveapi.api.hive_auth.boto3") as mock_boto,
    ):
        mock_api_cls.return_value.get_login_info.return_value = _LOGIN_INFO
        mock_boto.client.return_value = MagicMock()
        auth = HiveAuth(username=username, password=password, **kwargs)

    # auth.client is a MagicMock; _client_id / _pool_id / _region already set
    return auth


def _client_error(code: str, message: str = "msg") -> botocore.exceptions.ClientError:
    """Build a ClientError whose __class__.__name__ equals ``code``."""
    err = botocore.exceptions.ClientError(
        {"Error": {"Code": code, "Message": message}},
        "op",
    )
    err.__class__ = type(code, (botocore.exceptions.ClientError,), {})
    return err


def _endpoint_error() -> botocore.exceptions.EndpointConnectionError:
    return botocore.exceptions.EndpointConnectionError(
        endpoint_url="https://cognito.eu-west-1.amazonaws.com"
    )


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestHiveAuthInit:
    def test_pool_region_raises_value_error(self):
        from apyhiveapi.api.hive_auth import HiveAuth

        with pytest.raises(ValueError, match="pool_region"):
            HiveAuth(username="u", password="p", pool_region="eu-west-1")

    def test_file_flag_set_for_magic_username(self):
        auth = _make_auth(username="use@file.com", password="")
        assert auth.use_file is True

    def test_file_flag_not_set_for_normal_username(self):
        auth = _make_auth()
        assert auth.use_file is False

    def test_attributes_populated_from_login_info(self):
        auth = _make_auth()
        assert auth._pool_id == "eu-west-1_TestPool"
        assert auth._client_id == "test-client-id"
        assert auth._region == "eu-west-1"

    def test_device_credentials_stored(self):
        auth = _make_auth(
            device_group_key="dgk",
            device_key="dk",
            device_password="dp",
        )
        assert auth.device_group_key == "dgk"
        assert auth.device_key == "dk"
        assert auth.device_password == "dp"

    def test_client_secret_stored(self):
        auth = _make_auth(client_secret="secret")
        assert auth.client_secret == "secret"

    def test_access_token_initially_none(self):
        auth = _make_auth()
        assert auth.access_token is None

    def test_boto3_client_created_with_correct_region(self):
        from apyhiveapi.api.hive_auth import HiveAuth

        with (
            patch("apyhiveapi.api.hive_auth.HiveApi") as mock_api_cls,
            patch("apyhiveapi.api.hive_auth.boto3") as mock_boto,
        ):
            mock_api_cls.return_value.get_login_info.return_value = _LOGIN_INFO
            mock_boto.client.return_value = MagicMock()
            HiveAuth(username="u@example.com", password="p")

        mock_boto.client.assert_called_once()
        args, _ = mock_boto.client.call_args
        # First positional arg is "cognito-idp", second is region
        assert args[0] == "cognito-idp"
        assert args[1] == "eu-west-1"


# ---------------------------------------------------------------------------
# Tests: generate_random_small_a / calculate_a
# ---------------------------------------------------------------------------


class TestSrpHelpers:
    def test_generate_random_small_a_returns_int_less_than_big_n(self):
        auth = _make_auth()
        val = auth.generate_random_small_a()
        assert isinstance(val, int)
        assert 0 <= val < auth.big_n

    def test_calculate_a_returns_positive_int(self):
        auth = _make_auth()
        a = auth.calculate_a()
        assert isinstance(a, int)
        assert a > 0

    def test_large_a_value_stored_on_init(self):
        auth = _make_auth()
        # large_a_value is computed during __init__
        assert isinstance(auth.large_a_value, int)
        assert auth.large_a_value > 0

    def test_calculate_a_raises_value_error_when_big_a_mod_n_is_zero(self):
        """Test the safety check branch when big_a % big_n == 0."""
        auth = _make_auth()
        # Force pow() to return big_n itself (so big_a % big_n == 0)
        with patch("apyhiveapi.api.hive_auth.pow", return_value=auth.big_n):
            with pytest.raises(ValueError, match="Safety check for A failed"):
                auth.calculate_a()


# ---------------------------------------------------------------------------
# Tests: get_auth_params
# ---------------------------------------------------------------------------


class TestGetAuthParams:
    def test_returns_username_and_srp_a(self):
        auth = _make_auth()
        params = auth.get_auth_params()
        assert "USERNAME" in params
        assert params["USERNAME"] == "user@example.com"
        assert "SRP_A" in params

    def test_no_client_secret_no_secret_hash(self):
        auth = _make_auth()
        params = auth.get_auth_params()
        assert "SECRET_HASH" not in params

    def test_with_client_secret_adds_secret_hash(self):
        auth = _make_auth(client_secret="my-secret")
        params = auth.get_auth_params()
        assert "SECRET_HASH" in params
        # secret hash should be a non-empty string
        assert isinstance(params["SECRET_HASH"], str)
        assert len(params["SECRET_HASH"]) > 0


# ---------------------------------------------------------------------------
# Tests: get_secret_hash
# ---------------------------------------------------------------------------


class TestGetSecretHash:
    def test_returns_base64_string(self):
        import base64

        from apyhiveapi.api.hive_auth import HiveAuth

        result = HiveAuth.get_secret_hash("user@example.com", "client-id", "secret")
        # should be valid base64
        decoded = base64.standard_b64decode(result)
        assert len(decoded) == 32  # SHA-256 → 32 bytes

    def test_different_inputs_produce_different_hashes(self):
        from apyhiveapi.api.hive_auth import HiveAuth

        h1 = HiveAuth.get_secret_hash("user1@example.com", "client-id", "secret")
        h2 = HiveAuth.get_secret_hash("user2@example.com", "client-id", "secret")
        assert h1 != h2

    def test_same_inputs_are_deterministic(self):
        from apyhiveapi.api.hive_auth import HiveAuth

        h1 = HiveAuth.get_secret_hash("user@example.com", "client-id", "secret")
        h2 = HiveAuth.get_secret_hash("user@example.com", "client-id", "secret")
        assert h1 == h2


# ---------------------------------------------------------------------------
# Tests: generate_hash_device
# ---------------------------------------------------------------------------


class TestGenerateHashDevice:
    def test_returns_password_and_config_dict(self):
        auth = _make_auth()
        password, config = auth.generate_hash_device("group-key", "device-key")
        assert isinstance(password, str)
        assert len(password) > 0
        assert "PasswordVerifier" in config
        assert "Salt" in config

    def test_different_calls_produce_different_passwords(self):
        auth = _make_auth()
        pw1, _ = auth.generate_hash_device("group-key", "device-key")
        pw2, _ = auth.generate_hash_device("group-key", "device-key")
        # random device password — should differ
        assert pw1 != pw2


# ---------------------------------------------------------------------------
# Tests: login
# ---------------------------------------------------------------------------


class TestLogin:
    def test_file_mode_returns_file_response(self):
        auth = _make_auth(username="use@file.com", password="")
        result = auth.login()
        assert result == {"AuthenticationResult": {"AccessToken": "file"}}

    def test_user_not_found_raises_invalid_username(self):
        auth = _make_auth()
        auth.client.initiate_auth.side_effect = _client_error("UserNotFoundException")
        with pytest.raises(HiveInvalidUsername):
            auth.login()

    def test_endpoint_error_on_initiate_raises_api_error(self):
        auth = _make_auth()
        auth.client.initiate_auth.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            auth.login()

    def test_password_verifier_challenge_success(self):
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        expected_result = {"AuthenticationResult": {"AccessToken": "tok"}}
        auth.client.respond_to_auth_challenge.return_value = expected_result

        mock_challenge_response = {
            "TIMESTAMP": "Mon Jan 1 00:00:00 UTC 2024",
            "USERNAME": "user",
        }
        with patch.object(
            auth, "process_challenge", return_value=mock_challenge_response
        ):
            result = auth.login()

        assert result == expected_result

    def test_password_verifier_with_device_key_adds_device_key_to_challenge(self):
        auth = _make_auth(device_key="dk-123")
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth.client.respond_to_auth_challenge.return_value = {
            "AuthenticationResult": {"AccessToken": "tok"}
        }

        mock_challenge_response = {"TIMESTAMP": "ts", "USERNAME": "user"}
        with patch.object(
            auth, "process_challenge", return_value=mock_challenge_response
        ):
            auth.login()

        # Verify DEVICE_KEY was added to the challenge response
        _, call_kwargs = auth.client.respond_to_auth_challenge.call_args
        assert call_kwargs["ChallengeResponses"]["DEVICE_KEY"] == "dk-123"

    def test_not_authorized_on_respond_raises_invalid_password(self):
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth.client.respond_to_auth_challenge.side_effect = _client_error(
            "NotAuthorizedException"
        )

        mock_challenge_response = {"TIMESTAMP": "ts", "USERNAME": "user"}
        with patch.object(
            auth, "process_challenge", return_value=mock_challenge_response
        ):
            with pytest.raises(HiveInvalidPassword):
                auth.login()

    def test_resource_not_found_on_respond_raises_invalid_device_authentication(self):
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth.client.respond_to_auth_challenge.side_effect = _client_error(
            "ResourceNotFoundException"
        )

        mock_challenge_response = {"TIMESTAMP": "ts", "USERNAME": "user"}
        with patch.object(
            auth, "process_challenge", return_value=mock_challenge_response
        ):
            with pytest.raises(HiveInvalidDeviceAuthentication):
                auth.login()

    def test_endpoint_error_on_respond_raises_api_error(self):
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth.client.respond_to_auth_challenge.side_effect = _endpoint_error()

        mock_challenge_response = {"TIMESTAMP": "ts", "USERNAME": "user"}
        with patch.object(
            auth, "process_challenge", return_value=mock_challenge_response
        ):
            with pytest.raises(HiveApiError):
                auth.login()

    def test_unsupported_challenge_raises_not_implemented(self):
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "CUSTOM_CHALLENGE",
            "ChallengeParameters": {},
        }
        with pytest.raises(NotImplementedError, match="CUSTOM_CHALLENGE"):
            auth.login()

    def test_device_key_added_to_auth_params_when_present(self):
        auth = _make_auth(device_key="dk-xyz")
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth.client.respond_to_auth_challenge.return_value = {
            "AuthenticationResult": {"AccessToken": "tok"}
        }

        with patch.object(auth, "process_challenge", return_value={"TIMESTAMP": "ts"}):
            auth.login()

        _, call_kwargs = auth.client.initiate_auth.call_args
        assert call_kwargs["AuthParameters"]["DEVICE_KEY"] == "dk-xyz"

    def test_unmatched_client_error_on_initiate_falls_through_to_none_response(self):
        """ClientError with unrecognised code is silently dropped; response stays
        None and the next line raises TypeError when subscripting None."""
        auth = _make_auth()
        # A plain ClientError whose __class__.__name__ is "ClientError" (not
        # "UserNotFoundException")
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeOtherError", "Message": "msg"}}, "op"
        )
        auth.client.initiate_auth.side_effect = err
        # response stays None → response["ChallengeName"] raises TypeError
        with pytest.raises(TypeError):
            auth.login()

    def test_unmatched_endpoint_error_on_initiate_swallowed(self):
        """EndpointConnectionError with unrecognised class name is silently dropped;
        response stays None → TypeError when subscripting None."""
        auth = _make_auth()
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.initiate_auth.side_effect = err
        with pytest.raises(TypeError):
            auth.login()

    def test_unmatched_endpoint_error_on_respond_swallowed(self):
        """EndpointConnectionError with unrecognised class name on respond is silently
        swallowed; result stays None → returned as None."""
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.respond_to_auth_challenge.side_effect = err

        with patch.object(auth, "process_challenge", return_value={"TIMESTAMP": "ts"}):
            result = auth.login()

        assert result is None

    def test_unmatched_client_error_on_respond_returns_none(self):
        """ClientError with unrecognised code on respond_to_auth_challenge is silently
        swallowed; the function returns None (result never set)."""
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeOtherError", "Message": "msg"}}, "op"
        )
        auth.client.respond_to_auth_challenge.side_effect = err

        with patch.object(auth, "process_challenge", return_value={"TIMESTAMP": "ts"}):
            result = auth.login()

        assert result is None


# ---------------------------------------------------------------------------
# Tests: device_login
# ---------------------------------------------------------------------------


class TestDeviceLogin:
    def test_authentication_result_in_login_returns_directly(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        login_result = {"AuthenticationResult": {"AccessToken": "tok"}}
        with patch.object(auth, "login", return_value=login_result):
            result = auth.device_login()
        assert result is login_result

    def test_device_srp_auth_challenge_completes_device_login(self):
        auth = _make_auth(
            device_key="dk-1",
            device_group_key="dgk-1",
            device_password="dp-1",
        )
        login_result = {
            "ChallengeName": "DEVICE_SRP_AUTH",
            "ChallengeParameters": {"USERNAME": "user@example.com"},
        }
        initial_result = {
            "ChallengeParameters": {
                "USERNAME": "user@example.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            }
        }
        final_result = {"AuthenticationResult": {"AccessToken": "dev-tok"}}

        auth.client.respond_to_auth_challenge.side_effect = [
            initial_result,
            final_result,
        ]
        mock_device_challenge_resp = {"TIMESTAMP": "ts", "USERNAME": "user@example.com"}

        with (
            patch.object(auth, "login", return_value=login_result),
            patch.object(
                auth,
                "process_device_challenge",
                return_value=mock_device_challenge_resp,
            ),
        ):
            result = auth.device_login()

        assert result is final_result

    def test_sms_mfa_challenge_raises_reauth_required(self):
        auth = _make_auth(device_key="dk-1")
        login_result = {
            "ChallengeName": "SMS_MFA",
            "ChallengeParameters": {"Session": "sess-1"},
        }
        with patch.object(auth, "login", return_value=login_result):
            with pytest.raises(HiveReauthRequired):
                auth.device_login()

    def test_unknown_challenge_raises_invalid_device_authentication(self):
        auth = _make_auth(device_key="dk-1")
        login_result = {
            "ChallengeName": "UNKNOWN_CHALLENGE",
            "ChallengeParameters": {},
        }
        with patch.object(auth, "login", return_value=login_result):
            with pytest.raises(HiveInvalidDeviceAuthentication):
                auth.device_login()

    def test_endpoint_error_during_device_login_raises_api_error(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        login_result = {
            "ChallengeName": "DEVICE_SRP_AUTH",
            "ChallengeParameters": {"USERNAME": "user@example.com"},
        }
        auth.client.respond_to_auth_challenge.side_effect = _endpoint_error()

        with patch.object(auth, "login", return_value=login_result):
            with pytest.raises(HiveApiError):
                auth.device_login()

    def test_unmatched_endpoint_error_during_device_login_swallowed(self):
        """EndpointConnectionError with mismatched class name is silently dropped;
        result is undefined — NameError or UnboundLocalError is raised."""
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        login_result = {
            "ChallengeName": "DEVICE_SRP_AUTH",
            "ChallengeParameters": {"USERNAME": "user@example.com"},
        }
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.respond_to_auth_challenge.side_effect = err

        with patch.object(auth, "login", return_value=login_result):
            # exception swallowed → `result` is unbound → UnboundLocalError
            with pytest.raises((UnboundLocalError, Exception)):
                auth.device_login()


# ---------------------------------------------------------------------------
# Tests: sms_2fa
# ---------------------------------------------------------------------------


class TestSms2fa:
    def test_successful_sms_2fa_returns_result(self):
        auth = _make_auth()
        sms_result = {"AuthenticationResult": {"AccessToken": "sms-tok"}}
        auth.client.respond_to_auth_challenge.return_value = sms_result

        result = auth.sms_2fa("123456", {"Session": "sess-1"})
        assert result is sms_result

    def test_new_device_metadata_stores_keys(self):
        auth = _make_auth()
        sms_result = {
            "AuthenticationResult": {
                "AccessToken": "sms-tok",
                "NewDeviceMetadata": {
                    "DeviceGroupKey": "sms-grp",
                    "DeviceKey": "sms-dev",
                },
            }
        }
        auth.client.respond_to_auth_challenge.return_value = sms_result

        auth.sms_2fa("123456", {"Session": "sess-1"})

        assert auth.access_token == "sms-tok"
        assert auth.device_group_key == "sms-grp"
        assert auth.device_key == "sms-dev"

    def test_no_new_device_metadata_does_not_set_device_keys(self):
        auth = _make_auth()
        sms_result = {"AuthenticationResult": {"AccessToken": "sms-tok"}}
        auth.client.respond_to_auth_challenge.return_value = sms_result

        auth.sms_2fa("123456", {"Session": "sess-1"})

        # device_group_key stays None, access_token NOT set (no NewDeviceMetadata branch)
        assert auth.device_group_key is None
        assert auth.device_key is None

    def test_not_authorized_raises_invalid_2fa_code(self):
        auth = _make_auth()
        auth.client.respond_to_auth_challenge.side_effect = _client_error(
            "NotAuthorizedException"
        )
        with pytest.raises(HiveInvalid2FACode):
            auth.sms_2fa("000000", {"Session": "sess-1"})

    def test_code_mismatch_raises_invalid_2fa_code(self):
        auth = _make_auth()
        auth.client.respond_to_auth_challenge.side_effect = _client_error(
            "CodeMismatchException"
        )
        with pytest.raises(HiveInvalid2FACode):
            auth.sms_2fa("wrong", {"Session": "sess-1"})

    def test_endpoint_error_raises_api_error(self):
        auth = _make_auth()
        auth.client.respond_to_auth_challenge.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            auth.sms_2fa("123456", {"Session": "sess-1"})

    def test_unmatched_client_error_on_sms_2fa_swallowed(self):
        """ClientError with non-matching class name is silently swallowed; returns None."""
        auth = _make_auth()
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeOtherError", "Message": "msg"}}, "op"
        )
        auth.client.respond_to_auth_challenge.side_effect = err
        result = auth.sms_2fa("123456", {"Session": "sess-1"})
        assert result is None

    def test_unmatched_endpoint_error_on_sms_2fa_swallowed(self):
        """EndpointConnectionError with mismatched class name is swallowed; returns None."""
        auth = _make_auth()
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.respond_to_auth_challenge.side_effect = err
        result = auth.sms_2fa("123456", {"Session": "sess-1"})
        assert result is None

    def test_sms_code_is_coerced_to_str(self):
        auth = _make_auth()
        sms_result = {"AuthenticationResult": {"AccessToken": "tok"}}
        auth.client.respond_to_auth_challenge.return_value = sms_result

        auth.sms_2fa(123456, {"Session": "sess-1"})  # int code

        _, call_kwargs = auth.client.respond_to_auth_challenge.call_args
        assert call_kwargs["ChallengeResponses"]["SMS_MFA_CODE"] == "123456"


# ---------------------------------------------------------------------------
# Tests: device_registration / confirm_device / update_device_status
# ---------------------------------------------------------------------------


class TestDeviceRegistration:
    def test_device_registration_calls_confirm_and_update(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        auth.access_token = "access-tok"

        with (
            patch.object(auth, "confirm_device") as mock_confirm,
            patch.object(auth, "update_device_status") as mock_update,
        ):
            auth.device_registration(device_name="test-host")

        mock_confirm.assert_called_once_with("test-host")
        mock_update.assert_called_once()

    def test_confirm_device_uses_hostname_when_name_none(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        auth.access_token = "access-tok"
        auth.client.confirm_device.return_value = {}

        with patch.object(
            auth,
            "generate_hash_device",
            return_value=("pw", {"Salt": "s", "PasswordVerifier": "v"}),
        ):
            with patch(
                "apyhiveapi.api.hive_auth.socket.gethostname", return_value="my-host"
            ):
                auth.confirm_device(device_name=None)

        _, call_kwargs = auth.client.confirm_device.call_args
        assert call_kwargs["DeviceName"] == "my-host"

    def test_confirm_device_uses_provided_name(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        auth.access_token = "access-tok"
        auth.client.confirm_device.return_value = {}

        with patch.object(
            auth,
            "generate_hash_device",
            return_value=("pw", {"Salt": "s", "PasswordVerifier": "v"}),
        ):
            auth.confirm_device(device_name="custom-host")

        _, call_kwargs = auth.client.confirm_device.call_args
        assert call_kwargs["DeviceName"] == "custom-host"

    def test_confirm_device_stores_device_password(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        auth.access_token = "access-tok"
        auth.client.confirm_device.return_value = {}

        with patch.object(
            auth,
            "generate_hash_device",
            return_value=("generated-pw", {"Salt": "s", "PasswordVerifier": "v"}),
        ):
            auth.confirm_device(device_name="host")

        assert auth.device_password == "generated-pw"

    def test_confirm_device_endpoint_error_raises_api_error(self):
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        auth.access_token = "access-tok"
        auth.client.confirm_device.side_effect = _endpoint_error()

        with patch.object(
            auth,
            "generate_hash_device",
            return_value=("pw", {"Salt": "s", "PasswordVerifier": "v"}),
        ):
            with pytest.raises(HiveApiError):
                auth.confirm_device(device_name="host")

    def test_confirm_device_unmatched_endpoint_error_swallowed(self):
        """EndpointConnectionError with mismatched class name is silently dropped."""
        auth = _make_auth(device_key="dk-1", device_group_key="dgk-1")
        auth.access_token = "access-tok"
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.confirm_device.side_effect = err

        with patch.object(
            auth,
            "generate_hash_device",
            return_value=("pw", {"Salt": "s", "PasswordVerifier": "v"}),
        ):
            # exception swallowed → result stays None → returned
            result = auth.confirm_device(device_name="host")
        assert result is None

    def test_update_device_status_success(self):
        auth = _make_auth(device_key="dk-1")
        auth.access_token = "access-tok"
        auth.client.update_device_status.return_value = {}

        result = auth.update_device_status()
        assert result is not None

    def test_update_device_status_endpoint_error_raises_api_error(self):
        auth = _make_auth(device_key="dk-1")
        auth.access_token = "access-tok"
        auth.client.update_device_status.side_effect = _endpoint_error()

        with pytest.raises(HiveApiError):
            auth.update_device_status()

    def test_update_device_status_unmatched_endpoint_error_swallowed(self):
        """EndpointConnectionError with mismatched class name is silently dropped."""
        auth = _make_auth(device_key="dk-1")
        auth.access_token = "access-tok"
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.update_device_status.side_effect = err
        result = auth.update_device_status()
        assert result is None


# ---------------------------------------------------------------------------
# Tests: get_device_data
# ---------------------------------------------------------------------------


class TestGetDeviceData:
    def test_returns_tuple_of_device_credentials(self):
        auth = _make_auth(
            device_group_key="dgk",
            device_key="dk",
            device_password="dp",
        )
        result = auth.get_device_data()
        assert result == ("dgk", "dk", "dp")

    def test_returns_none_values_when_not_set(self):
        auth = _make_auth()
        dgk, dk, dp = auth.get_device_data()
        assert dgk is None
        assert dk is None
        assert dp is None


# ---------------------------------------------------------------------------
# Tests: refresh_token
# ---------------------------------------------------------------------------


class TestRefreshToken:
    def test_no_device_key_sends_only_refresh_token(self):
        auth = _make_auth()
        expected = {"AuthenticationResult": {"AccessToken": "new-tok"}}
        auth.client.initiate_auth.return_value = expected

        result = auth.refresh_token("refresh-tok")

        assert result is expected
        _, call_kwargs = auth.client.initiate_auth.call_args
        assert call_kwargs["AuthParameters"] == {"REFRESH_TOKEN": "refresh-tok"}

    def test_with_device_key_includes_device_key_in_params(self):
        auth = _make_auth(device_key="dk-refresh")
        expected = {"AuthenticationResult": {"AccessToken": "new-tok"}}
        auth.client.initiate_auth.return_value = expected

        result = auth.refresh_token("refresh-tok")

        assert result is expected
        _, call_kwargs = auth.client.initiate_auth.call_args
        assert call_kwargs["AuthParameters"]["DEVICE_KEY"] == "dk-refresh"
        assert call_kwargs["AuthParameters"]["REFRESH_TOKEN"] == "refresh-tok"

    def test_uses_refresh_token_auth_flow(self):
        auth = _make_auth()
        auth.client.initiate_auth.return_value = {}

        auth.refresh_token("tok")

        _, call_kwargs = auth.client.initiate_auth.call_args
        assert call_kwargs["AuthFlow"] == "REFRESH_TOKEN_AUTH"

    def test_endpoint_error_raises_api_error(self):
        auth = _make_auth()
        auth.client.initiate_auth.side_effect = _endpoint_error()

        with pytest.raises(HiveApiError):
            auth.refresh_token("tok")

    def test_unmatched_endpoint_error_on_refresh_token_swallowed(self):
        """EndpointConnectionError with mismatched class name is silently dropped; returns None."""
        auth = _make_auth()
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.initiate_auth.side_effect = err
        result = auth.refresh_token("tok")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: forget_device
# ---------------------------------------------------------------------------


class TestForgetDevice:
    def test_forget_device_success(self):
        auth = _make_auth()
        auth.client.forget_device.return_value = {}

        result = auth.forget_device("access-tok", "dev-key")

        auth.client.forget_device.assert_called_once_with(
            AccessToken="access-tok",
            DeviceKey="dev-key",
        )
        assert result == {}

    def test_not_authorized_raises_invalid_2fa_code(self):
        auth = _make_auth()
        auth.client.forget_device.side_effect = _client_error("NotAuthorizedException")

        with pytest.raises(HiveInvalid2FACode):
            auth.forget_device("access-tok", "dev-key")

    def test_endpoint_error_raises_api_error(self):
        auth = _make_auth()
        # forget_device checks for ResourceNotFoundException on EndpointConnectionError
        err = _endpoint_error()
        err.__class__ = type(
            "ResourceNotFoundException",
            (botocore.exceptions.EndpointConnectionError,),
            {},
        )
        auth.client.forget_device.side_effect = err

        with pytest.raises(HiveApiError):
            auth.forget_device("access-tok", "dev-key")

    def test_unmatched_endpoint_error_on_forget_device_swallowed(self):
        """EndpointConnectionError with mismatched class name is silently dropped; returns None."""
        auth = _make_auth()
        err = _endpoint_error()
        err.__class__ = type(
            "SomeOtherEndpointError", (botocore.exceptions.EndpointConnectionError,), {}
        )
        auth.client.forget_device.side_effect = err
        result = auth.forget_device("access-tok", "dev-key")
        assert result is None

    def test_unmatched_client_error_on_forget_device_swallowed(self):
        """ClientError with non-matching class name is silently dropped; returns None."""
        auth = _make_auth()
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "SomeOtherError", "Message": "msg"}}, "op"
        )
        auth.client.forget_device.side_effect = err
        result = auth.forget_device("access-tok", "dev-key")
        assert result is None


# ---------------------------------------------------------------------------
# Tests: module-level helper functions
# ---------------------------------------------------------------------------


class TestHelperFunctions:
    def test_hex_to_long(self):
        from apyhiveapi.api.hive_auth import hex_to_long

        assert hex_to_long("ff") == 255
        assert hex_to_long("0") == 0
        assert hex_to_long("10") == 16

    def test_get_random_returns_int(self):
        from apyhiveapi.api.hive_auth import get_random

        val = get_random(16)
        assert isinstance(val, int)
        assert val >= 0

    def test_hash_sha256_returns_64_char_hex(self):
        from apyhiveapi.api.hive_auth import hash_sha256

        result = hash_sha256(b"hello")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_hex_hash_returns_64_char_hex(self):
        from apyhiveapi.api.hive_auth import hex_hash

        # "00" is a valid hex string
        result = hex_hash("00")
        assert len(result) == 64

    def test_long_to_hex(self):
        from apyhiveapi.api.hive_auth import long_to_hex

        assert long_to_hex(255) == "ff"
        assert long_to_hex(0) == "0"
        assert long_to_hex(16) == "10"

    def test_pad_hex_odd_length(self):
        from apyhiveapi.api.hive_auth import pad_hex

        result = pad_hex("f")
        assert result == "0f"

    def test_pad_hex_starts_with_high_nibble(self):
        from apyhiveapi.api.hive_auth import pad_hex

        # 'a' starts with high nibble → gets "00" prefix
        result = pad_hex("ab")
        assert result == "00ab"

    def test_pad_hex_normal_even_length(self):
        from apyhiveapi.api.hive_auth import pad_hex

        # "12" has even length and starts with '1' (not high nibble)
        result = pad_hex("12")
        assert result == "12"

    def test_pad_hex_integer_input(self):
        from apyhiveapi.api.hive_auth import pad_hex

        # 255 → "ff" → starts with 'f' (high nibble) → "00ff"
        result = pad_hex(255)
        assert result == "00ff"

    def test_compute_hkdf_returns_16_bytes(self):
        from apyhiveapi.api.hive_auth import compute_hkdf

        ikm = bytearray(b"input_key_material")
        salt = bytearray(b"salt_value")
        result = compute_hkdf(ikm, salt)
        assert isinstance(result, bytes)
        assert len(result) == 16

    def test_calculate_u_returns_nonzero_for_distinct_inputs(self):
        from apyhiveapi.api.hive_auth import calculate_u

        # large_a and large_b should be non-zero to get non-zero u
        result = calculate_u(12345678, 87654321)
        assert isinstance(result, int)
        assert result >= 0


# ---------------------------------------------------------------------------
# Tests: get_password_authentication_key
# ---------------------------------------------------------------------------


class TestGetPasswordAuthenticationKey:
    def _valid_server_b_hex(self, auth):
        """Return a server_b hex value that won't produce U == 0."""
        # Use a big prime-like value that differs from large_a
        # to guarantee U != 0.  We pick something clearly distinct.
        return format(auth.large_a_value + 1, "x")

    def test_returns_16_byte_hkdf(self):
        auth = _make_auth()
        # Need a valid hex salt and a server_b that won't produce U==0
        server_b_hex = self._valid_server_b_hex(auth)
        salt_hex = "00aabbcc"  # valid hex salt
        result = auth.get_password_authentication_key(
            "user@example.com", "pass", server_b_hex, salt_hex
        )
        assert isinstance(result, bytes)
        assert len(result) == 16

    def test_different_passwords_produce_different_keys(self):
        auth = _make_auth()
        server_b_hex = self._valid_server_b_hex(auth)
        salt_hex = "00aabbcc"

        key1 = auth.get_password_authentication_key(
            "user@example.com", "pass1", server_b_hex, salt_hex
        )
        key2 = auth.get_password_authentication_key(
            "user@example.com", "pass2", server_b_hex, salt_hex
        )
        assert key1 != key2

    def test_raises_value_error_when_u_is_zero(self):
        """Test the U == 0 guard branch."""

        auth = _make_auth()
        server_b_hex = "00aabbcc"
        salt_hex = "00aabbcc"
        with patch("apyhiveapi.api.hive_auth.calculate_u", return_value=0):
            with pytest.raises(ValueError, match="U cannot be zero"):
                auth.get_password_authentication_key(
                    "user@example.com", "pass", server_b_hex, salt_hex
                )


# ---------------------------------------------------------------------------
# Tests: get_device_authentication_key
# ---------------------------------------------------------------------------


class TestGetDeviceAuthenticationKey:
    def test_returns_16_byte_hkdf(self):
        auth = _make_auth()
        # server_b_value here is an integer (not hex string), per the source
        server_b_value = auth.large_a_value + 1
        salt = "00aabbcc"  # hex string for the salt param
        result = auth.get_device_authentication_key(
            "group-key", "device-key", "device-password", server_b_value, salt
        )
        assert isinstance(result, bytes)
        assert len(result) == 16

    def test_raises_value_error_when_u_is_zero(self):
        """Test the U == 0 guard branch."""
        auth = _make_auth()
        server_b_value = auth.large_a_value + 1
        salt = "00aabbcc"
        with patch("apyhiveapi.api.hive_auth.calculate_u", return_value=0):
            with pytest.raises(ValueError, match="U cannot be zero"):
                auth.get_device_authentication_key(
                    "group-key", "device-key", "device-password", server_b_value, salt
                )


# ---------------------------------------------------------------------------
# Tests: process_challenge
# ---------------------------------------------------------------------------


class TestProcessChallenge:
    def _make_challenge_params(self):
        import base64

        return {
            "USER_ID_FOR_SRP": "user@example.com",
            "SALT": "00aabbcc",
            "SRP_B": "ccddee",
            "SECRET_BLOCK": base64.standard_b64encode(b"secret-block-bytes").decode(
                "utf-8"
            ),
        }

    def test_returns_required_keys(self):
        auth = _make_auth()
        params = self._make_challenge_params()
        fake_hkdf = bytes(16)  # 16 zero bytes, valid HMAC key

        with patch.object(
            auth, "get_password_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_challenge(params)

        assert "TIMESTAMP" in response
        assert "USERNAME" in response
        assert "PASSWORD_CLAIM_SECRET_BLOCK" in response
        assert "PASSWORD_CLAIM_SIGNATURE" in response

    def test_sets_user_id_from_challenge_parameters(self):
        auth = _make_auth()
        params = self._make_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_password_authentication_key", return_value=fake_hkdf
        ):
            auth.process_challenge(params)

        assert auth.user_id == "user@example.com"

    def test_secret_block_preserved_in_response(self):
        auth = _make_auth()
        params = self._make_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_password_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_challenge(params)

        assert response["PASSWORD_CLAIM_SECRET_BLOCK"] == params["SECRET_BLOCK"]

    def test_with_client_secret_adds_secret_hash(self):
        auth = _make_auth(client_secret="my-secret")
        params = self._make_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_password_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_challenge(params)

        assert "SECRET_HASH" in response

    def test_without_client_secret_no_secret_hash(self):
        auth = _make_auth()
        params = self._make_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_password_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_challenge(params)

        assert "SECRET_HASH" not in response


# ---------------------------------------------------------------------------
# Tests: process_device_challenge
# ---------------------------------------------------------------------------


class TestProcessDeviceChallenge:
    def _make_device_challenge_params(self):
        import base64

        return {
            "USERNAME": "user@example.com",
            "SALT": "00aabbcc",
            "SRP_B": "ccddee",
            "SECRET_BLOCK": base64.standard_b64encode(b"secret-block-bytes").decode(
                "utf-8"
            ),
        }

    def test_returns_required_keys(self):
        auth = _make_auth(
            device_key="dk-1",
            device_group_key="dgk-1",
            device_password="dp-1",
        )
        params = self._make_device_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_device_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_device_challenge(params)

        assert "TIMESTAMP" in response
        assert "USERNAME" in response
        assert "PASSWORD_CLAIM_SECRET_BLOCK" in response
        assert "PASSWORD_CLAIM_SIGNATURE" in response
        assert response["DEVICE_KEY"] == "dk-1"

    def test_username_from_challenge_params(self):
        auth = _make_auth(
            device_key="dk-1",
            device_group_key="dgk-1",
            device_password="dp-1",
        )
        params = self._make_device_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_device_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_device_challenge(params)

        assert response["USERNAME"] == "user@example.com"

    def test_with_client_secret_adds_secret_hash(self):
        auth = _make_auth(
            device_key="dk-1",
            device_group_key="dgk-1",
            device_password="dp-1",
            client_secret="my-secret",
        )
        params = self._make_device_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_device_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_device_challenge(params)

        assert "SECRET_HASH" in response

    def test_without_client_secret_no_secret_hash(self):
        auth = _make_auth(
            device_key="dk-1",
            device_group_key="dgk-1",
            device_password="dp-1",
        )
        params = self._make_device_challenge_params()
        fake_hkdf = bytes(16)

        with patch.object(
            auth, "get_device_authentication_key", return_value=fake_hkdf
        ):
            response = auth.process_device_challenge(params)

        assert "SECRET_HASH" not in response
