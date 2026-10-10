"""Tests for SessionAuthMixin — update_tokens, login, sms2fa, hive_refresh_tokens."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveInvalid2FACode,
    HiveReauthRequired,
    HiveRefreshTokenExpired,
    HiveUnknownConfiguration,
)
from apyhiveapi.helper.hivedataclasses import SessionConfig, SessionTokens
from apyhiveapi.session.auth import SessionAuthMixin

AUTH_RESULT = {
    "AuthenticationResult": {
        "IdToken": "id-tok",
        "AccessToken": "acc-tok",
        "RefreshToken": "ref-tok",
        "ExpiresIn": 3600,
    }
}


def _make_stub():
    """Create a concrete SessionAuthMixin instance with mocked dependencies."""

    class StubAuth(SessionAuthMixin):
        """Concrete subclass used only for testing."""

    s = StubAuth()
    s.auth = MagicMock()
    s.auth.DEVICE_VERIFIER_CHALLENGE = "DEVICE_SRP_AUTH"
    s.auth.SMS_MFA_CHALLENGE = "SMS_MFA"
    s.auth.login = AsyncMock()
    s.auth.device_login = AsyncMock()
    s.auth.sms_2fa = AsyncMock()
    s.auth.refresh_token = AsyncMock()
    s.tokens = SessionTokens()
    s.tokens.token_data = {"refreshToken": "rt", "token": "", "accessToken": ""}
    s.config = SessionConfig()
    s.helper = MagicMock()
    s.helper.sanitize_payload = MagicMock(return_value={})
    s._refresh_threshold = 0.90
    s._refresh_lock = asyncio.Lock()
    return s


class TestUpdateTokens:
    """Tests for SessionAuthMixin.update_tokens()."""

    async def test_authentication_result_sets_all_tokens(self):
        """AuthenticationResult payload writes all three token fields."""
        s = _make_stub()
        await s.update_tokens(AUTH_RESULT)
        assert s.tokens.token_data["token"] == "id-tok"
        assert s.tokens.token_data["accessToken"] == "acc-tok"
        assert s.tokens.token_data["refreshToken"] == "ref-tok"

    async def test_update_expiry_time_false_skips_token_created(self):
        """update_expiry_time=False leaves token_created unchanged."""
        s = _make_stub()
        before = s.tokens.token_created
        await s.update_tokens(AUTH_RESULT, update_expiry_time=False)
        assert s.tokens.token_created == before

    async def test_flat_token_dict_sets_all_keys(self):
        """Flat token dict (no AuthenticationResult wrapper) sets all three keys."""
        s = _make_stub()
        flat = {"token": "t", "refreshToken": "r", "accessToken": "a"}
        await s.update_tokens(flat)
        assert s.tokens.token_data["token"] == "t"
        assert s.tokens.token_data["refreshToken"] == "r"
        assert s.tokens.token_data["accessToken"] == "a"

    async def test_expires_in_updates_token_expiry(self):
        """ExpiresIn field updates token_expiry timedelta."""
        s = _make_stub()
        await s.update_tokens(AUTH_RESULT)
        assert s.tokens.token_expiry == timedelta(seconds=3600)


class TestLogin:
    """Tests for SessionAuthMixin.login()."""

    async def test_auth_result_calls_update_tokens_and_returns(self):
        """Successful login with AuthenticationResult updates tokens."""
        s = _make_stub()
        s.auth.login.return_value = AUTH_RESULT
        result = await s.login()
        assert "AuthenticationResult" in result

    async def test_sms_mfa_challenge_returned_directly(self):
        """SMS_MFA challenge is returned to caller without raising."""
        s = _make_stub()
        s.auth.login.return_value = {"ChallengeName": "SMS_MFA"}
        result = await s.login()
        assert result["ChallengeName"] == "SMS_MFA"

    async def test_unknown_challenge_raises(self):
        """Unrecognised challenge name raises HiveUnknownConfiguration."""
        s = _make_stub()
        s.auth.login.return_value = {"ChallengeName": "TOTALLY_UNKNOWN"}
        with pytest.raises(HiveUnknownConfiguration):
            await s.login()

    async def test_no_auth_raises(self):
        """Missing auth object raises HiveUnknownConfiguration."""
        s = _make_stub()
        s.auth = None
        with pytest.raises(HiveUnknownConfiguration):
            await s.login()

    async def test_device_srp_challenge_routes_to_device_login(self):
        """DEVICE_SRP_AUTH challenge calls device_login."""
        s = _make_stub()
        s.auth.login.return_value = {"ChallengeName": "DEVICE_SRP_AUTH"}
        s.auth.device_login.return_value = AUTH_RESULT
        await s.login()
        s.auth.device_login.assert_called_once()


class TestHandleDeviceLoginChallenge:
    """Tests for SessionAuthMixin._handle_device_login_challenge()."""

    async def test_success_calls_update_tokens(self):
        """Successful device login returns result with AuthenticationResult."""
        s = _make_stub()
        s.auth.device_login.return_value = AUTH_RESULT
        result = await s._handle_device_login_challenge({})
        assert "AuthenticationResult" in result

    async def test_sms_mfa_response_raises_reauth(self):
        """SMS_MFA response from device_login raises HiveReauthRequired."""
        s = _make_stub()
        s.auth.device_login.return_value = {"ChallengeName": "SMS_MFA"}
        with pytest.raises(HiveReauthRequired):
            await s._handle_device_login_challenge({})


class TestSms2fa:
    """Tests for SessionAuthMixin.sms2fa()."""

    async def test_success_calls_update_tokens(self):
        """Successful 2FA returns result with AuthenticationResult."""
        s = _make_stub()
        s.auth.sms_2fa.return_value = AUTH_RESULT
        result = await s.sms2fa("123456", {"session": "data"})
        assert "AuthenticationResult" in result

    async def test_invalid_code_reraises(self):
        """Invalid 2FA code re-raises HiveInvalid2FACode."""
        s = _make_stub()
        s.auth.sms_2fa.side_effect = HiveInvalid2FACode()
        with pytest.raises(HiveInvalid2FACode):
            await s.sms2fa("bad", {})


class TestHiveRefreshTokens:
    """Tests for SessionAuthMixin.hive_refresh_tokens()."""

    async def test_not_expired_returns_none_without_calling_refresh(self):
        """Token not yet at threshold — refresh_token is not called."""
        s = _make_stub()
        s.tokens.token_created = datetime.now()
        s.tokens.token_expiry = timedelta(hours=1)
        result = await s.hive_refresh_tokens()
        assert result is None
        s.auth.refresh_token.assert_not_called()

    async def test_expired_calls_refresh_and_update_tokens(self):
        """Expired token triggers refresh_token and updates stored tokens."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.return_value = AUTH_RESULT
        await s.hive_refresh_tokens()
        s.auth.refresh_token.assert_called_once()
        assert s.tokens.token_data["token"] == "id-tok"

    async def test_refresh_token_expired_falls_back_to_retry_login(self):
        """HiveRefreshTokenExpired triggers _retry_login fallback."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.side_effect = HiveRefreshTokenExpired()
        s._retry_login = AsyncMock()
        await s.hive_refresh_tokens()
        s._retry_login.assert_called_once()

    async def test_force_refresh_expired_raises_reauth(self):
        """force_refresh=True with failed refresh raises HiveReauthRequired."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.side_effect = HiveRefreshTokenExpired()
        with pytest.raises(HiveReauthRequired):
            await s.hive_refresh_tokens(force_refresh=True)
