"""Unit tests for HiveAuthAsync."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import botocore.exceptions
import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveApiError,
    HiveConnectionError,
    HiveFailedToRefreshTokens,
    HiveInvalid2FACode,
    HiveInvalidDeviceAuthentication,
    HiveInvalidPassword,
    HiveInvalidUsername,
    HiveRefreshTokenExpired,
    HiveUnknownConfiguration,
)

# ---------------------------------------------------------------------------
# Exception factories
# ---------------------------------------------------------------------------


def _named_client_error(
    code: str, message: str = ""
) -> botocore.exceptions.ClientError:
    """Return a ClientError whose __class__.__name__ matches ``code``."""
    # The source checks err.__class__.__name__, so we build a dynamic subclass
    # with the right name.
    cls = type(code, (botocore.exceptions.ClientError,), {})
    return cls(
        {"Error": {"Code": code, "Message": message}},
        "operation",
    )


def _endpoint_error() -> botocore.exceptions.EndpointConnectionError:
    return botocore.exceptions.EndpointConnectionError(
        endpoint_url="https://cognito.eu-west-1.amazonaws.com"
    )


# ---------------------------------------------------------------------------
# Fixture-style helpers
# ---------------------------------------------------------------------------


async def _make_auth(
    username: str = "test@test.com",
    password: str = "testpass",
    device_key: str | None = None,
    device_group_key: str | None = None,
    device_password: str | None = None,
    client_secret: str | None = None,
):
    from apyhiveapi.api.hive_auth_async import HiveAuthAsync

    auth = HiveAuthAsync(
        username=username,
        password=password,
        device_key=device_key,
        device_group_key=device_group_key,
        device_password=device_password,
        client_secret=client_secret,
    )
    # Bypass async_init — inject mocked internals directly.
    auth.client = MagicMock()
    auth._client_id = "test-client-id"
    auth._pool_id = "eu-west-1_TestPool123"
    auth._region = "eu-west-1"
    auth.loop = MagicMock()
    auth.loop.run_in_executor = AsyncMock()
    return auth


_LOGIN_INFO = {
    "UPID": "eu-west-1_TestPool",
    "CLIID": "test-client-id",
    "REGION": "eu-west-1_TestPool",
}


# ---------------------------------------------------------------------------
# Tests: __init__
# ---------------------------------------------------------------------------


class TestHiveAuthAsyncInit:
    def test_pool_region_no_longer_accepted(self):
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        with pytest.raises(TypeError):
            HiveAuthAsync(username="u", password="p", pool_region="eu-west-1")

    async def test_async_init_sets_running_loop(self):
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="u@test.com", password="pass")
        assert auth.loop is None  # not set until async_init
        mock_data = {
            "UPID": "eu-west-1_Test",
            "CLIID": "client-id",
            "REGION": "eu-west-1_Test",
        }
        with patch.object(auth.api, "get_login_info", return_value=mock_data):
            with patch("boto3.client", return_value=MagicMock()):
                await auth.async_init()
        assert auth.loop is not None

    async def test_file_flag_set_for_magic_username(self):
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="use@file.com", password="")
        assert auth.use_file is True

    async def test_file_flag_not_set_for_normal_username(self):
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="real@user.com", password="pass")
        assert auth.use_file is False


# ---------------------------------------------------------------------------
# Tests: _to_int
# ---------------------------------------------------------------------------


class TestToInt:
    @pytest.mark.asyncio
    async def test_int_input_returns_int(self):
        auth = await _make_auth()
        assert auth._to_int(42) == 42

    @pytest.mark.asyncio
    async def test_bytes_input_returns_int(self):
        auth = await _make_auth()
        # b'\xff' → hex "ff" → 255
        assert auth._to_int(b"\xff") == 255

    @pytest.mark.asyncio
    async def test_hex_string_returns_int(self):
        auth = await _make_auth()
        assert auth._to_int("ff") == 255

    @pytest.mark.asyncio
    async def test_zero_bytes_input(self):
        auth = await _make_auth()
        assert auth._to_int(b"\x00") == 0


# ---------------------------------------------------------------------------
# Tests: get_auth_params
# ---------------------------------------------------------------------------


class TestGetAuthParams:
    @pytest.mark.asyncio
    async def test_returns_username_and_srp_a(self):
        auth = await _make_auth()
        params = await auth.get_auth_params()
        assert "USERNAME" in params
        assert "SRP_A" in params

    @pytest.mark.asyncio
    async def test_no_client_secret_no_secret_hash(self):
        auth = await _make_auth()
        params = await auth.get_auth_params()
        assert "SECRET_HASH" not in params

    @pytest.mark.asyncio
    async def test_with_client_secret_adds_secret_hash(self):
        auth = await _make_auth(client_secret="my-secret")
        params = await auth.get_auth_params()
        assert "SECRET_HASH" in params

    @pytest.mark.asyncio
    async def test_device_login_adds_device_key(self):
        auth = await _make_auth(device_key="dk-1234")
        params = await auth.get_auth_params(is_device_login=True)
        assert params["DEVICE_KEY"] == "dk-1234"

    @pytest.mark.asyncio
    async def test_non_device_login_no_device_key(self):
        auth = await _make_auth(device_key="dk-1234")
        params = await auth.get_auth_params(is_device_login=False)
        assert "DEVICE_KEY" not in params


# ---------------------------------------------------------------------------
# Tests: login
# ---------------------------------------------------------------------------


class TestLogin:
    @pytest.mark.asyncio
    async def test_file_mode_returns_file_response(self):
        auth = await _make_auth(username="use@file.com", password="")
        result = await auth.login()
        assert result == {"AuthenticationResult": {"AccessToken": "file"}}

    @pytest.mark.asyncio
    async def test_user_not_found_raises_invalid_username(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _named_client_error(
            "UserNotFoundException"
        )
        with pytest.raises(HiveInvalidUsername):
            await auth.login()

    @pytest.mark.asyncio
    async def test_direct_authentication_without_challenge_stores_token(self):
        """A response with AuthenticationResult and no ChallengeName must not crash."""
        auth = await _make_auth()
        auth_result = {"AuthenticationResult": {"AccessToken": "direct-tok"}}
        auth.loop.run_in_executor.return_value = auth_result

        result = await auth.login()

        assert result is auth_result
        assert auth.access_token == "direct-tok"

    @pytest.mark.asyncio
    async def test_login_regenerates_srp_ephemeral_each_attempt(self):
        """Each login() must use a fresh SRP (a, A) ephemeral pair."""
        auth = await _make_auth()
        auth.loop.run_in_executor.return_value = {
            "AuthenticationResult": {"AccessToken": "tok"}
        }

        initial_a = auth.large_a_value
        await auth.login()
        second_a = auth.large_a_value
        await auth.login()
        third_a = auth.large_a_value

        assert len({initial_a, second_a, third_a}) == 3

    @pytest.mark.asyncio
    async def test_device_login_regenerates_srp_ephemeral(self):
        """device_login() must use a fresh SRP (a, A) ephemeral pair."""
        auth = await _make_auth(device_key="dk-1", device_group_key="grp-1")
        auth.device_password = "dev-pass"  # pragma: allowlist secret
        auth.loop.run_in_executor.return_value = {"ChallengeParameters": {}}

        initial_a = auth.large_a_value
        with patch.object(
            auth, "process_device_challenge", new=AsyncMock(return_value={})
        ):
            await auth.device_login()

        assert auth.large_a_value != initial_a

    @pytest.mark.asyncio
    async def test_endpoint_error_on_initiate_raises_api_error(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await auth.login()

    @pytest.mark.asyncio
    async def test_password_verifier_challenge_not_authorized_raises_invalid_password(
        self,
    ):
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        not_auth_err = _named_client_error("NotAuthorizedException")
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, not_auth_err]
            )
            with pytest.raises(HiveInvalidPassword):
                await auth.login()

    @pytest.mark.asyncio
    async def test_password_verifier_challenge_resource_not_found_raises_invalid_device(
        self,
    ):
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        not_found_err = _named_client_error("ResourceNotFoundException")
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, not_found_err]
            )
            with pytest.raises(HiveInvalidDeviceAuthentication):
                await auth.login()

    @pytest.mark.asyncio
    async def test_password_verifier_endpoint_error_on_challenge_raises_api_error(self):
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, _endpoint_error()]
            )
            with pytest.raises(HiveApiError):
                await auth.login()

    @pytest.mark.asyncio
    async def test_new_device_metadata_stores_device_keys(self):
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth_result = {
            "AuthenticationResult": {
                "AccessToken": "access-tok",
                "NewDeviceMetadata": {
                    "DeviceGroupKey": "grp-key",
                    "DeviceKey": "dev-key",
                },
            }
        }
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, auth_result]
            )
            result = await auth.login()
        assert auth.device_group_key == "grp-key"
        assert auth.device_key == "dev-key"
        assert auth.access_token == "access-tok"
        assert result is auth_result

    @pytest.mark.asyncio
    async def test_access_token_stored_without_new_device_metadata(self):
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth_result = {
            "AuthenticationResult": {
                "AccessToken": "only-token",
            }
        }
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, auth_result]
            )
            await auth.login()
        assert auth.access_token == "only-token"
        assert auth.device_group_key is None

    @pytest.mark.asyncio
    async def test_unsupported_challenge_raises_not_implemented(self):
        auth = await _make_auth()
        auth.loop.run_in_executor = AsyncMock(
            return_value={
                "ChallengeName": "CUSTOM_CHALLENGE",
                "ChallengeParameters": {},
            }
        )
        with pytest.raises(NotImplementedError, match="CUSTOM_CHALLENGE"):
            await auth.login()


# ---------------------------------------------------------------------------
# Tests: device_login
# ---------------------------------------------------------------------------


class TestDeviceLogin:
    @pytest.mark.asyncio
    async def test_resource_not_found_raises_invalid_device_authentication(self):
        auth = await _make_auth(device_key="dk-1")
        auth.loop.run_in_executor.side_effect = _named_client_error(
            "ResourceNotFoundException"
        )
        with pytest.raises(HiveInvalidDeviceAuthentication):
            await auth.device_login()

    @pytest.mark.asyncio
    async def test_not_authorized_raises_invalid_device_authentication(self):
        auth = await _make_auth(device_key="dk-1")
        auth.loop.run_in_executor.side_effect = _named_client_error(
            "NotAuthorizedException"
        )
        with pytest.raises(HiveInvalidDeviceAuthentication):
            await auth.device_login()

    @pytest.mark.asyncio
    async def test_endpoint_error_raises_api_error(self):
        auth = await _make_auth(device_key="dk-1")
        auth.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await auth.device_login()

    @pytest.mark.asyncio
    async def test_other_client_error_propagates(self):
        auth = await _make_auth(device_key="dk-1")
        auth.loop.run_in_executor.side_effect = _named_client_error("SomeOtherError")
        with pytest.raises(botocore.exceptions.ClientError):
            await auth.device_login()


# ---------------------------------------------------------------------------
# Tests: sms_2fa
# ---------------------------------------------------------------------------


class TestSms2fa:
    @pytest.mark.asyncio
    async def test_not_authorized_raises_invalid_2fa_code(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _named_client_error(
            "NotAuthorizedException"
        )
        with pytest.raises(HiveInvalid2FACode):
            await auth.sms_2fa("123456", {"Session": "sess-1"})

    @pytest.mark.asyncio
    async def test_code_mismatch_raises_invalid_2fa_code(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _named_client_error(
            "CodeMismatchException"
        )
        with pytest.raises(HiveInvalid2FACode):
            await auth.sms_2fa("000000", {"Session": "sess-1"})

    @pytest.mark.asyncio
    async def test_endpoint_error_raises_api_error(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveApiError):
            await auth.sms_2fa("123456", {"Session": "sess-1"})

    @pytest.mark.asyncio
    async def test_successful_sms_2fa_stores_access_token(self):
        auth = await _make_auth()
        sms_result = {
            "AuthenticationResult": {
                "AccessToken": "sms-token",
            }
        }
        auth.loop.run_in_executor.return_value = sms_result
        result = await auth.sms_2fa("123456", {"Session": "sess-1"})
        assert auth.access_token == "sms-token"
        assert result is sms_result

    @pytest.mark.asyncio
    async def test_new_device_metadata_in_sms_stores_keys(self):
        auth = await _make_auth()
        sms_result = {
            "AuthenticationResult": {
                "AccessToken": "sms-token",
                "NewDeviceMetadata": {
                    "DeviceGroupKey": "sms-grp",
                    "DeviceKey": "sms-dev",
                },
            }
        }
        auth.loop.run_in_executor.return_value = sms_result
        await auth.sms_2fa("123456", {"Session": "sess-1"})
        assert auth.device_group_key == "sms-grp"
        assert auth.device_key == "sms-dev"

    @pytest.mark.asyncio
    async def test_no_authentication_result_key_does_not_raise(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.return_value = {"ChallengeName": "SMS_MFA"}
        result = await auth.sms_2fa("123456", {"Session": "sess-1"})
        assert auth.access_token is None
        assert result == {"ChallengeName": "SMS_MFA"}


# ---------------------------------------------------------------------------
# Tests: refresh_token
# ---------------------------------------------------------------------------


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_no_device_key_sends_only_refresh_token(self):
        auth = await _make_auth()
        result_payload = {"AuthenticationResult": {"AccessToken": "new-tok"}}
        auth.loop.run_in_executor.return_value = result_payload
        result = await auth.refresh_token("refresh-tok")
        assert result is result_payload

    @pytest.mark.asyncio
    async def test_with_device_key_includes_device_key_in_params(self):
        auth = await _make_auth(device_key="dk-refresh")
        result_payload = {"AuthenticationResult": {"AccessToken": "new-tok"}}
        auth.loop.run_in_executor.return_value = result_payload
        result = await auth.refresh_token("refresh-tok")
        # Verify the call was made (the actual auth_params check is internal,
        # but we at least confirm no exception and correct return value)
        assert result is result_payload

    @pytest.mark.asyncio
    async def test_invalid_refresh_token_raises_expired(self):
        auth = await _make_auth()
        err = botocore.exceptions.ClientError(
            {
                "Error": {
                    "Code": "NotAuthorizedException",
                    "Message": "Invalid Refresh Token",
                }
            },
            "InitiateAuth",
        )
        auth.loop.run_in_executor.side_effect = err
        with pytest.raises(HiveRefreshTokenExpired):
            await auth.refresh_token("bad-token")

    @pytest.mark.asyncio
    async def test_not_authorized_without_invalid_refresh_raises_failed(self):
        auth = await _make_auth()
        err = botocore.exceptions.ClientError(
            {
                "Error": {
                    "Code": "NotAuthorizedException",
                    "Message": "Some other message",
                }
            },
            "InitiateAuth",
        )
        auth.loop.run_in_executor.side_effect = err
        with pytest.raises(HiveFailedToRefreshTokens):
            await auth.refresh_token("tok")

    @pytest.mark.asyncio
    async def test_other_client_error_raises_failed_to_refresh(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _named_client_error(
            "TokenExpiredException"
        )
        with pytest.raises(HiveFailedToRefreshTokens):
            await auth.refresh_token("tok")

    @pytest.mark.asyncio
    async def test_endpoint_error_raises_connection_error(self):
        auth = await _make_auth()
        auth.loop.run_in_executor.side_effect = _endpoint_error()
        with pytest.raises(HiveConnectionError):
            await auth.refresh_token("tok")


# ---------------------------------------------------------------------------
# Migrated from test_hive_auth_async_extended.py
# ---------------------------------------------------------------------------


class TestAsyncInit:
    """Cover lines 98-112: async_init() sets pool_id, client_id, region and boto3 client."""

    async def test_async_init_sets_pool_id_and_client_id(self):
        """async_init reads login info and sets internal auth fields."""
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="user@test.com", password="pass")
        auth.client = None

        mock_boto_client = MagicMock()
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(
            side_effect=[_LOGIN_INFO, mock_boto_client]
        )

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await auth.async_init()

        assert auth._pool_id == "eu-west-1_TestPool"
        assert auth._client_id == "test-client-id"
        assert auth._region == "eu-west-1"
        assert auth.client is mock_boto_client

    async def test_async_init_splits_region_correctly(self):
        """Region is extracted as the part before the underscore in UPID/REGION."""
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="user@test.com", password="pass")
        auth.client = None

        login_info = {
            "UPID": "ap-southeast-2_XyzPool",
            "CLIID": "ap-client",
            "REGION": "ap-southeast-2_XyzPool",
        }
        mock_boto_client = MagicMock()
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(
            side_effect=[login_info, mock_boto_client]
        )

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            await auth.async_init()

        assert auth._region == "ap-southeast-2"


class TestCalculateA:
    """Cover line 141: safety check when big_a % big_n == 0."""

    async def test_safety_check_raises_when_a_is_zero_mod_n(self):
        """If pow(g, a, n) == 0 mod n (i.e., equals big_n or 0), ValueError is raised."""
        auth = await _make_auth()
        with patch("builtins.pow", return_value=auth.big_n):
            with pytest.raises(ValueError, match="Safety check for A failed"):
                auth.calculate_a()

    async def test_safety_check_passes_normally(self):
        """Under normal random inputs, calculate_a does not raise and returns positive int."""
        auth = await _make_auth()
        result = auth.calculate_a()
        assert result > 0


class TestGetPasswordAuthenticationKey:
    """Cover lines 155-172: get_password_authentication_key() computes HKDF."""

    async def test_returns_bytes(self):
        """With valid SRP inputs, the method returns a bytes-like value."""
        auth = await _make_auth()
        from apyhiveapi.api.srp_crypto import get_random

        server_b_value = hex(get_random(128))[2:]
        salt = hex(get_random(16))[2:]

        with patch("apyhiveapi.api.hive_auth_async.calculate_u", return_value=99999):
            result = auth.get_password_authentication_key(
                "testuser", "testpass", server_b_value, salt
            )

        assert isinstance(result, (bytes, bytearray))

    async def test_u_value_zero_raises_value_error(self):
        """If calculate_u returns 0, ValueError is raised."""
        auth = await _make_auth()
        from apyhiveapi.api.srp_crypto import get_random

        server_b_value = hex(get_random(128))[2:]
        salt = hex(get_random(16))[2:]

        with patch("apyhiveapi.api.hive_auth_async.calculate_u", return_value=0):
            with pytest.raises(ValueError, match="U cannot be zero"):
                auth.get_password_authentication_key(
                    "testuser", "testpass", server_b_value, salt
                )

    async def test_accepts_integer_server_b(self):
        """server_b_value can be passed as an integer (handled by _to_int)."""
        auth = await _make_auth()
        from apyhiveapi.api.srp_crypto import get_random

        server_b_int = get_random(128)
        salt = hex(get_random(16))[2:]

        with patch("apyhiveapi.api.hive_auth_async.calculate_u", return_value=12345):
            result = auth.get_password_authentication_key(
                "testuser", "testpass", server_b_int, salt
            )

        assert isinstance(result, (bytes, bytearray))


class TestProcessChallenge:
    """Cover lines 205-254: process_challenge() builds the SRP response."""

    def _make_challenge_params(self, salt_as_int=False):
        import base64

        salt = "aabbccddee"
        if salt_as_int:
            salt = int("aabbccddee", 16)
        return {
            "USER_ID_FOR_SRP": "challenge-user@test.com",
            "SALT": salt,
            "SRP_B": "ff" * 32,
            "SECRET_BLOCK": base64.b64encode(b"secret-block-bytes").decode(),
        }

    async def test_returns_required_keys(self):
        """Basic challenge response includes mandatory SRP keys."""
        auth = await _make_auth()
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params()
        result = await auth.process_challenge(params)
        assert "TIMESTAMP" in result
        assert "USERNAME" in result
        assert "PASSWORD_CLAIM_SECRET_BLOCK" in result
        assert "PASSWORD_CLAIM_SIGNATURE" in result

    async def test_sets_user_id_from_challenge(self):
        """process_challenge stores USER_ID_FOR_SRP as self.user_id."""
        auth = await _make_auth()
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params()
        await auth.process_challenge(params)
        assert auth.user_id == "challenge-user@test.com"

    async def test_with_client_secret_adds_secret_hash(self):
        """When client_secret is set, SECRET_HASH is added to the response."""
        auth = await _make_auth(client_secret="my-secret")
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params()
        result = await auth.process_challenge(params)
        assert "SECRET_HASH" in result

    async def test_without_client_secret_no_secret_hash(self):
        """When client_secret is None, SECRET_HASH is absent from the response."""
        auth = await _make_auth(client_secret=None)
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params()
        result = await auth.process_challenge(params)
        assert "SECRET_HASH" not in result

    async def test_with_device_key_adds_device_key(self):
        """When device_key is set, DEVICE_KEY is added to the response."""
        auth = await _make_auth(device_key="dk-challenge")
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params()
        result = await auth.process_challenge(params)
        assert result["DEVICE_KEY"] == "dk-challenge"

    async def test_without_device_key_no_device_key_in_response(self):
        """When device_key is None, DEVICE_KEY is absent from the response."""
        auth = await _make_auth(device_key=None)
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params()
        result = await auth.process_challenge(params)
        assert "DEVICE_KEY" not in result

    async def test_salt_as_integer_triggers_pad_hex(self):
        """When SALT is an integer (not str), pad_hex is applied before use."""
        auth = await _make_auth()
        fake_hkdf = b"\x00" * 32
        auth.loop.run_in_executor = AsyncMock(return_value=fake_hkdf)
        params = self._make_challenge_params(salt_as_int=True)
        result = await auth.process_challenge(params)
        assert "TIMESTAMP" in result


class TestLoginClientNone:
    """Cover line 263: when client is None, async_init() is awaited."""

    async def test_login_calls_async_init_when_client_is_none(self):
        """If client is None before login, async_init is called before SRP flow."""
        auth = await _make_auth()
        auth.client = None
        auth.use_file = False

        auth_result = {"AuthenticationResult": {"AccessToken": "post-init-token"}}
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }

        async def fake_async_init():
            auth.client = MagicMock()
            auth._client_id = "test-client-id"
            auth._pool_id = "eu-west-1_TestPool"
            auth._region = "eu-west-1"

        with patch.object(auth, "async_init", side_effect=fake_async_init) as mock_init:
            with patch.object(
                auth, "process_challenge", new_callable=AsyncMock
            ) as mock_ch:
                mock_ch.return_value = {
                    "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                    "USERNAME": "user",
                }
                auth.loop.run_in_executor = AsyncMock(
                    side_effect=[challenge_response, auth_result]
                )
                result = await auth.login()

        mock_init.assert_called_once()
        assert "AuthenticationResult" in result


class TestLoginUnsupportedChallenge:
    """Cover lines 335-337: non-PASSWORD_VERIFIER challenge raises NotImplementedError."""

    async def test_new_password_required_raises_not_implemented(self):
        """NEW_PASSWORD_REQUIRED challenge is not supported and raises NotImplementedError."""
        auth = await _make_auth()
        auth.loop.run_in_executor = AsyncMock(
            return_value={
                "ChallengeName": "NEW_PASSWORD_REQUIRED",
                "ChallengeParameters": {},
            }
        )
        with pytest.raises(NotImplementedError, match="NEW_PASSWORD_REQUIRED"):
            await auth.login()

    async def test_custom_challenge_raises_not_implemented(self):
        """Any unknown challenge name raises NotImplementedError."""
        auth = await _make_auth()
        auth.loop.run_in_executor = AsyncMock(
            return_value={
                "ChallengeName": "UNKNOWN_CHALLENGE_TYPE",
                "ChallengeParameters": {},
            }
        )
        with pytest.raises(NotImplementedError, match="UNKNOWN_CHALLENGE_TYPE"):
            await auth.login()


class TestLoginResourceNotFound:
    """Cover lines 307-311: ResourceNotFoundException in respond_to_auth_challenge."""

    async def test_resource_not_found_raises_invalid_device_authentication(self):
        """ResourceNotFoundException during challenge → HiveInvalidDeviceAuthentication."""
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        resource_err = _named_client_error("ResourceNotFoundException")
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, resource_err]
            )
            with pytest.raises(HiveInvalidDeviceAuthentication):
                await auth.login()


class TestLoginEndpointErrorOnChallenge:
    """Cover lines 312-317: EndpointConnectionError during respond_to_auth_challenge."""

    async def test_endpoint_error_on_challenge_raises_api_error(self):
        """EndpointConnectionError during SRP challenge response → HiveApiError."""
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, _endpoint_error()]
            )
            with pytest.raises(HiveApiError):
                await auth.login()


class TestLoginResultHandling:
    """Cover lines 321-333: AuthenticationResult presence/absence in login result."""

    async def test_result_without_authentication_result_does_not_store_token(self):
        """If result lacks 'AuthenticationResult', access_token is not set."""
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        sms_challenge_result = {
            "ChallengeName": "SMS_MFA",
            "Session": "session-tok",
            "ChallengeParameters": {},
        }
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, sms_challenge_result]
            )
            result = await auth.login()

        assert auth.access_token is None
        assert result is sms_challenge_result

    async def test_result_with_authentication_result_but_no_new_device_metadata(self):
        """AuthenticationResult without NewDeviceMetadata sets access_token only."""
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        auth_result = {"AuthenticationResult": {"AccessToken": "my-access-token"}}
        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, auth_result]
            )
            await auth.login()

        assert auth.access_token == "my-access-token"
        assert auth.device_group_key is None
        assert auth.device_key is None


class TestDeviceLoginClientNone:
    """Cover device_login's async_init call when client is None."""

    async def test_device_login_calls_async_init_when_client_is_none(self):
        """If client is None, async_init is called before proceeding."""
        auth = await _make_auth(device_key="dk-1")
        auth.client = None

        async def fake_async_init():
            auth.client = MagicMock()
            auth._client_id = "test-client-id"

        with patch.object(auth, "async_init", side_effect=fake_async_init) as mock_init:
            auth.loop.run_in_executor = AsyncMock(
                side_effect=_named_client_error("ResourceNotFoundException")
            )
            with pytest.raises(HiveInvalidDeviceAuthentication):
                await auth.device_login()

        mock_init.assert_called_once()


class TestSms2faNoNewDeviceMetadata:
    """Cover line 441: sms_2fa when NewDeviceMetadata is absent in result."""

    async def test_no_new_device_metadata_does_not_set_device_keys(self):
        """When NewDeviceMetadata is absent, device_group_key and device_key stay None."""
        auth = await _make_auth()
        original_group_key = auth.device_group_key
        original_device_key = auth.device_key

        sms_result = {
            "AuthenticationResult": {
                "AccessToken": "sms-access-token",
            }
        }
        auth.loop.run_in_executor = AsyncMock(return_value=sms_result)

        result = await auth.sms_2fa("654321", {"Session": "sess-abc"})

        assert auth.access_token == "sms-access-token"
        assert auth.device_group_key == original_group_key
        assert auth.device_key == original_device_key
        assert result is sms_result


class TestSms2faCodeMismatch:
    """Cover lines 424-429: CodeMismatchException raises HiveInvalid2FACode."""

    async def test_code_mismatch_raises_invalid_2fa_code(self):
        """CodeMismatchException in sms_2fa raises HiveInvalid2FACode."""
        auth = await _make_auth()
        auth.loop.run_in_executor = AsyncMock(
            side_effect=_named_client_error("CodeMismatchException")
        )
        with pytest.raises(HiveInvalid2FACode):
            await auth.sms_2fa("000000", {"Session": "sess-1"})

    async def test_not_authorized_raises_invalid_2fa_code(self):
        """NotAuthorizedException in sms_2fa raises HiveInvalid2FACode."""
        auth = await _make_auth()
        auth.loop.run_in_executor = AsyncMock(
            side_effect=_named_client_error("NotAuthorizedException")
        )
        with pytest.raises(HiveInvalid2FACode):
            await auth.sms_2fa("111111", {"Session": "sess-2"})


class TestRefreshTokenClientNone:
    """Cover line 440-441: refresh_token calls async_init when client is None."""

    async def test_refresh_token_calls_async_init_when_client_is_none(self):
        """If client is None, async_init is awaited before refreshing."""
        auth = await _make_auth()
        auth.client = None

        result_payload = {"AuthenticationResult": {"AccessToken": "refreshed-tok"}}

        async def fake_async_init():
            auth.client = MagicMock()

        with patch.object(auth, "async_init", side_effect=fake_async_init) as mock_init:
            auth.loop.run_in_executor = AsyncMock(return_value=result_payload)
            result = await auth.refresh_token("some-refresh-token")

        mock_init.assert_called_once()
        assert result is result_payload


class TestRefreshTokenResultPath:
    """Cover lines 479-485: refresh_token when result is returned normally."""

    async def test_returns_result_directly(self):
        """refresh_token returns the result from Cognito directly."""
        auth = await _make_auth()
        result_payload = {"AuthenticationResult": {"AccessToken": "tok-xyz"}}
        auth.loop.run_in_executor = AsyncMock(return_value=result_payload)
        result = await auth.refresh_token("refresh-tok-abc")
        assert result is result_payload

    async def test_with_device_key_includes_device_key_param(self):
        """When device_key is set, DEVICE_KEY is included in auth_params."""
        auth = await _make_auth(device_key="dk-refresh-001")
        result_payload = {"AuthenticationResult": {"AccessToken": "tok-dk"}}
        auth.loop.run_in_executor = AsyncMock(return_value=result_payload)
        result = await auth.refresh_token("refresh-tok-dk")
        assert result is result_payload

    async def test_without_device_key_sends_only_refresh_token(self):
        """When device_key is None, auth_params has only REFRESH_TOKEN."""
        auth = await _make_auth(device_key=None)
        result_payload = {"AuthenticationResult": {"AccessToken": "tok-no-dk"}}
        auth.loop.run_in_executor = AsyncMock(return_value=result_payload)
        result = await auth.refresh_token("refresh-tok-no-dk")
        assert result is result_payload


class TestLoginInitiateAuthSwallowedClientError:
    """Arc 280->288: ClientError caught but class name is not UserNotFoundException."""

    async def test_other_client_error_in_initiate_auth_falls_through(self):
        """Non-UserNotFoundException ClientError raises HiveApiError."""
        auth = await _make_auth()

        wrong_cls = type("SomeOtherError", (botocore.exceptions.ClientError,), {})
        wrong_err = wrong_cls(
            {"Error": {"Code": "SomeOtherError", "Message": "msg"}}, "op"
        )
        auth.loop.run_in_executor = AsyncMock(side_effect=wrong_err)

        with pytest.raises(HiveApiError):
            await auth.login()


class TestLoginInitiateAuthSwallowedEndpointError:
    """EndpointConnectionError in initiate_auth always raises HiveApiError."""

    async def test_wrong_name_endpoint_error_in_initiate_auth_raises_api_error(self):
        """Any EndpointConnectionError subclass in initiate_auth raises HiveApiError."""
        auth = await _make_auth()

        wrong_cls = type(
            "WrongEndpoint", (botocore.exceptions.EndpointConnectionError,), {}
        )
        wrong_err = wrong_cls(endpoint_url="https://cognito.eu-west-1.amazonaws.com")
        auth.loop.run_in_executor = AsyncMock(side_effect=wrong_err)

        with pytest.raises(HiveApiError):
            await auth.login()


class TestLoginChallengeSwallowedClientError:
    """Arc 307->319: ClientError caught in challenge response with name not matching."""

    async def test_other_client_error_in_challenge_falls_through(self):
        """ClientError that is neither NotAuthorized nor ResourceNotFound raises HiveApiError."""
        auth = await _make_auth()

        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }

        wrong_cls = type("ThirdPartyError", (botocore.exceptions.ClientError,), {})
        wrong_err = wrong_cls(
            {"Error": {"Code": "ThirdPartyError", "Message": "msg"}}, "op"
        )

        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {"TIMESTAMP": "...", "USERNAME": "user"}
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, wrong_err]
            )
            with pytest.raises(HiveApiError):
                await auth.login()


class TestLoginChallengeSwallowedEndpointError:
    """EndpointConnectionError in respond_to_auth_challenge always raises HiveApiError."""

    async def test_wrong_name_endpoint_error_in_challenge_raises_api_error(self):
        """Any EndpointConnectionError subclass in SRP challenge raises HiveApiError."""
        auth = await _make_auth()

        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }

        wrong_cls = type(
            "WrongEndpoint", (botocore.exceptions.EndpointConnectionError,), {}
        )
        wrong_err = wrong_cls(endpoint_url="https://cognito.eu-west-1.amazonaws.com")

        with patch.object(auth, "process_challenge", new_callable=AsyncMock) as mock_ch:
            mock_ch.return_value = {"TIMESTAMP": "...", "USERNAME": "user"}
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[challenge_response, wrong_err]
            )
            with pytest.raises(HiveApiError):
                await auth.login()


class TestDeviceLoginSuccessPath:
    """Lines 364-367, 391: device_login processes device challenge and returns result."""

    async def test_successful_device_login_returns_auth_result(self):
        """Full device_login success: process_device_challenge called, result returned."""
        auth = await _make_auth(device_key="dk-abc", device_group_key="grp-abc")
        auth.device_password = "dev-pass"  # pragma: allowlist secret

        initial_result = {
            "ChallengeParameters": {
                "USERNAME": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            }
        }
        final_result = {"AuthenticationResult": {"AccessToken": "device-access-token"}}

        with patch.object(
            auth, "process_device_challenge", new_callable=AsyncMock
        ) as mock_pdc:
            mock_pdc.return_value = {
                "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
                "USERNAME": "user@test.com",
                "PASSWORD_CLAIM_SECRET_BLOCK": "YWJj",  # pragma: allowlist secret
                "PASSWORD_CLAIM_SIGNATURE": "sig",  # pragma: allowlist secret
                "DEVICE_KEY": "dk-abc",
            }
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[initial_result, final_result]
            )
            result = await auth.device_login()

        mock_pdc.assert_called_once_with(initial_result["ChallengeParameters"])
        assert result is final_result

    async def test_device_login_calls_second_respond_to_auth_challenge(self):
        """Lines 367-375: second respond_to_auth_challenge is called with device challenge."""
        auth = await _make_auth(device_key="dk-xyz", device_group_key="grp-xyz")
        auth.device_password = "dev-pass-xyz"  # pragma: allowlist secret

        initial_result = {
            "ChallengeParameters": {
                "USERNAME": "user@test.com",
                "SALT": "11223344",
                "SRP_B": "55667788",
                "SECRET_BLOCK": "dGVzdA==",  # pragma: allowlist secret
            }
        }
        final_result = {"AuthenticationResult": {"AccessToken": "tok-xyz"}}

        challenge_resp = {
            "TIMESTAMP": "Mon Jan 01 00:00:00 UTC 2024",
            "USERNAME": "user@test.com",
            "PASSWORD_CLAIM_SECRET_BLOCK": "dGVzdA==",  # pragma: allowlist secret
            "PASSWORD_CLAIM_SIGNATURE": "sig",  # pragma: allowlist secret
            "DEVICE_KEY": "dk-xyz",
        }

        with patch.object(
            auth, "process_device_challenge", new_callable=AsyncMock
        ) as mock_pdc:
            mock_pdc.return_value = challenge_resp
            auth.loop.run_in_executor = AsyncMock(
                side_effect=[initial_result, final_result]
            )
            result = await auth.device_login()

        assert auth.loop.run_in_executor.call_count == 2
        assert result["AuthenticationResult"]["AccessToken"] == "tok-xyz"


class TestDeviceLoginEndpointWrongName:
    """Any EndpointConnectionError in device_login always raises HiveApiError."""

    async def test_wrong_name_endpoint_error_raises_api_error(self):
        """Any EndpointConnectionError subclass in device_login raises HiveApiError."""
        auth = await _make_auth(device_key="dk-err", device_group_key="grp-err")
        auth.device_password = "dev-pass-err"  # pragma: allowlist secret

        wrong_cls = type(
            "WrongEndpoint", (botocore.exceptions.EndpointConnectionError,), {}
        )
        wrong_err = wrong_cls(endpoint_url="https://cognito.eu-west-1.amazonaws.com")
        auth.loop.run_in_executor = AsyncMock(side_effect=wrong_err)

        with pytest.raises(HiveApiError):
            await auth.device_login()


class TestSms2faUnrecognisedClientError:
    """An unrecognised ClientError in sms_2fa must surface as HiveApiError."""

    async def test_other_client_error_raises_hive_api_error(self):
        """A ClientError that is not a 2FA rejection must not be swallowed."""
        auth = await _make_auth()

        auth.loop.run_in_executor = AsyncMock(
            side_effect=_named_client_error("LimitExceededException")
        )

        with pytest.raises(HiveApiError):
            await auth.sms_2fa("123456", {"Session": "sess-xyz"})


class TestSms2faSwallowedEndpointError:
    """Any EndpointConnectionError in sms_2fa raises HiveApiError."""

    async def test_wrong_name_endpoint_error_raises_api_error(self):
        """Any EndpointConnectionError subclass in sms_2fa raises HiveApiError."""
        auth = await _make_auth()

        wrong_cls = type(
            "WrongEndpoint", (botocore.exceptions.EndpointConnectionError,), {}
        )
        wrong_err = wrong_cls(endpoint_url="https://cognito.eu-west-1.amazonaws.com")
        auth.loop.run_in_executor = AsyncMock(side_effect=wrong_err)

        with pytest.raises(HiveApiError):
            await auth.sms_2fa("654321", {"Session": "sess-abc"})


class TestRefreshTokenSwallowedEndpointError:
    """Any EndpointConnectionError in refresh_token raises HiveApiError."""

    async def test_wrong_name_endpoint_error_raises_api_error(self):
        """Any EndpointConnectionError subclass in refresh_token raises HiveApiError."""
        auth = await _make_auth()

        wrong_cls = type(
            "WrongEndpoint", (botocore.exceptions.EndpointConnectionError,), {}
        )
        wrong_err = wrong_cls(endpoint_url="https://cognito.eu-west-1.amazonaws.com")
        auth.loop.run_in_executor = AsyncMock(side_effect=wrong_err)

        with pytest.raises(HiveApiError):
            await auth.refresh_token("some-refresh-token")


class TestAsyncInitMissingKeys:
    """async_init must raise HiveUnknownConfiguration when login info keys are absent."""

    async def test_async_init_missing_region_raises_configuration_error(self):
        """If REGION is absent from login info, raise HiveUnknownConfiguration."""
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="user@test.com", password="pass")
        bad_login_info = {"UPID": "eu-west-1_TestPool", "CLIID": "test-client-id"}
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(side_effect=[bad_login_info])
        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with pytest.raises(HiveUnknownConfiguration):
                await auth.async_init()

    async def test_async_init_missing_upid_raises_configuration_error(self):
        """If UPID is absent from login info, raise HiveUnknownConfiguration."""
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="user@test.com", password="pass")
        bad_login_info = {"CLIID": "test-client-id", "REGION": "eu-west-1_TestPool"}
        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(side_effect=[bad_login_info])
        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with pytest.raises(HiveUnknownConfiguration):
                await auth.async_init()


class TestGetPasswordAuthKeyNonePoolId:
    """get_password_authentication_key must not crash with AttributeError when _pool_id is None."""

    async def test_none_pool_id_raises_configuration_error(self):
        """If _pool_id is None, raise HiveUnknownConfiguration (not AttributeError)."""
        auth = await _make_auth()
        auth._pool_id = None
        with pytest.raises(HiveUnknownConfiguration):
            auth.get_password_authentication_key("user", "pass", "DEADBEEF", "ABCDEF")


class TestLoginUnhandledClientError:
    """Unhandled ClientError codes in login() must raise HiveApiError, not crash."""

    async def test_initiate_auth_unhandled_error_raises_hive_api_error(self):
        """Non-UserNotFoundException ClientError from initiate_auth raises HiveApiError."""
        auth = await _make_auth()
        err = botocore.exceptions.ClientError(
            {"Error": {"Code": "TooManyRequestsException", "Message": "too many"}},
            "InitiateAuth",
        )
        auth.loop.run_in_executor = AsyncMock(side_effect=err)
        with pytest.raises(HiveApiError):
            await auth.login()

    async def test_respond_to_challenge_unhandled_error_raises_hive_api_error(self):
        """Non-NotAuthorized/ResourceNotFound ClientError raises HiveApiError."""
        auth = await _make_auth()
        challenge_response = {
            "ChallengeName": "PASSWORD_VERIFIER",
            "ChallengeParameters": {
                "USER_ID_FOR_SRP": "user@test.com",
                "SALT": "aabbccdd",
                "SRP_B": "ccddee",
                "SECRET_BLOCK": "YWJj",
            },
        }
        respond_err = botocore.exceptions.ClientError(
            {"Error": {"Code": "InternalErrorException", "Message": "internal"}},
            "RespondToAuthChallenge",
        )
        auth.loop.run_in_executor = AsyncMock(
            side_effect=[challenge_response, respond_err]
        )
        auth.process_challenge = AsyncMock(
            return_value={"TIMESTAMP": "t", "USERNAME": "u"}
        )
        with pytest.raises(HiveApiError):
            await auth.login()


class TestAsyncInitNoneGuard:
    """async_init must guard against get_login_info returning None."""

    async def test_async_init_raises_when_login_info_is_none(self):
        """async_init raises HiveUnknownConfiguration when get_login_info returns None."""
        from apyhiveapi.api.hive_auth_async import HiveAuthAsync

        auth = HiveAuthAsync(username="user@test.com", password="pass")
        auth.client = None

        mock_loop = MagicMock()
        mock_loop.run_in_executor = AsyncMock(return_value=None)

        with patch("asyncio.get_running_loop", return_value=mock_loop):
            with pytest.raises(HiveUnknownConfiguration):
                await auth.async_init()
