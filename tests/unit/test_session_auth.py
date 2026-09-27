"""Extended branch-coverage tests for SessionAuthMixin."""

# pylint: disable=attribute-defined-outside-init,too-few-public-methods,protected-access
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi.helper.hive_exceptions import (
    HiveApiError,
    HiveFailedToRefreshTokens,
    HiveInvalidUsername,
    HiveReauthRequired,
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
    """Return a concrete SessionAuthMixin instance with mocked dependencies."""

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


# ---------------------------------------------------------------------------
# update_tokens — extra branches
# ---------------------------------------------------------------------------


class TestUpdateTokensExtended:
    """Tests for update_tokens branches not covered by the main test file."""

    async def test_auth_result_without_refresh_token_still_sets_token_and_access(self):
        """AuthenticationResult missing RefreshToken still sets IdToken and AccessToken."""
        s = _make_stub()
        old_refresh = s.tokens.token_data["refreshToken"]
        payload = {
            "AuthenticationResult": {
                "IdToken": "new-id",
                "AccessToken": "new-acc",
                # no RefreshToken key
                "ExpiresIn": 1800,
            }
        }
        await s.update_tokens(payload)
        assert s.tokens.token_data["token"] == "new-id"
        assert s.tokens.token_data["accessToken"] == "new-acc"
        # refreshToken must NOT have been overwritten
        assert s.tokens.token_data["refreshToken"] == old_refresh

    async def test_flat_token_dict_without_expires_in_leaves_token_expiry_unchanged(
        self,
    ):
        """Flat token dict with no ExpiresIn does not alter token_expiry."""
        s = _make_stub()
        original_expiry = s.tokens.token_expiry
        flat = {"token": "t2", "refreshToken": "r2", "accessToken": "a2"}
        await s.update_tokens(flat)
        assert s.tokens.token_expiry == original_expiry

    async def test_auth_result_with_update_expiry_true_sets_token_created(self):
        """update_expiry_time=True (default) updates token_created timestamp."""
        s = _make_stub()
        before = s.tokens.token_created
        await s.update_tokens(AUTH_RESULT, update_expiry_time=True)
        assert s.tokens.token_created > before

    async def test_auth_result_missing_id_token_does_not_raise(self):
        """AuthenticationResult with only AccessToken (e.g. file mode) must not crash."""
        s = _make_stub()
        payload = {"AuthenticationResult": {"AccessToken": "only-access"}}
        await s.update_tokens(payload)
        assert s.tokens.token_data["accessToken"] == "only-access"
        # IdToken absent — the session token must not have been overwritten
        assert s.tokens.token_data["token"] == ""

    async def test_flat_dict_missing_access_token_does_not_raise(self):
        """A flat token dict without accessToken must not crash."""
        s = _make_stub()
        flat = {"token": "t-only"}
        await s.update_tokens(flat)
        assert s.tokens.token_data["token"] == "t-only"
        assert s.tokens.token_data["accessToken"] == ""

    async def test_auth_result_missing_access_token_does_not_raise(self):
        """AuthenticationResult with only IdToken must not crash."""
        s = _make_stub()
        payload = {"AuthenticationResult": {"IdToken": "only-id"}}
        await s.update_tokens(payload)
        assert s.tokens.token_data["token"] == "only-id"
        assert s.tokens.token_data["accessToken"] == ""


# ---------------------------------------------------------------------------
# _retry_with_backoff — re-raise semantics
# ---------------------------------------------------------------------------


class _NeedsArgsError(Exception):
    """Exception type that cannot be constructed without arguments."""

    def __init__(self, first, second):
        super().__init__(f"{first}/{second}")


class TestRetryWithBackoffReraise:
    """Without reraise_as, the original exception instance must propagate."""

    async def test_original_exception_instance_propagates(self):
        """The last caught error is re-raised as-is, not re-instantiated."""
        s = _make_stub()
        original = _NeedsArgsError("a", "b")

        async def _always_fail():
            raise original

        with pytest.raises(_NeedsArgsError) as excinfo:
            await s._retry_with_backoff(_always_fail, delays=(0,))

        assert excinfo.value is original

    async def test_empty_delays_raises_runtime_error(self):
        """With no attempts configured the defensive fallback raises RuntimeError."""
        s = _make_stub()

        async def _never_called():
            raise AssertionError("should not run")

        with pytest.raises(RuntimeError, match="exhausted"):
            await s._retry_with_backoff(_never_called, delays=())

    async def test_reraise_as_still_translates_exception_type(self):
        """When reraise_as is given the error is translated with chaining."""
        s = _make_stub()

        async def _always_fail():
            raise ValueError("boom")

        with pytest.raises(HiveReauthRequired) as excinfo:
            await s._retry_with_backoff(
                _always_fail, delays=(0,), reraise_as=HiveReauthRequired
            )

        assert isinstance(excinfo.value.__cause__, ValueError)


# ---------------------------------------------------------------------------
# _handle_device_login_challenge — extra branch
# ---------------------------------------------------------------------------


class TestHandleDeviceLoginChallengeExtended:
    """Tests for _handle_device_login_challenge branches not covered elsewhere."""

    async def test_result_without_auth_result_returns_directly_without_updating_tokens(
        self,
    ):
        """Result with no AuthenticationResult is returned as-is; tokens remain unchanged."""
        s = _make_stub()
        plain_result = {"ok": True}
        s.auth.device_login.return_value = plain_result
        result = await s._handle_device_login_challenge({})
        assert result == plain_result
        # Tokens must be untouched — refreshToken is still the stub default
        assert s.tokens.token_data["refreshToken"] == "rt"
        assert s.tokens.token_data["token"] == ""


# ---------------------------------------------------------------------------
# sms2fa — extra branches
# ---------------------------------------------------------------------------


class TestSms2faExtended:
    """Tests for sms2fa branches not covered by the main test file."""

    async def test_no_auth_raises_unknown_config(self):
        """sms2fa with auth=None raises HiveUnknownConfiguration."""
        s = _make_stub()
        s.auth = None
        with pytest.raises(HiveUnknownConfiguration):
            await s.sms2fa("123456", {})

    async def test_api_error_reraises(self):
        """HiveApiError from auth.sms_2fa propagates unchanged."""
        s = _make_stub()
        s.auth.sms_2fa.side_effect = HiveApiError()
        with pytest.raises(HiveApiError):
            await s.sms2fa("123456", {})

    async def test_result_without_auth_result_returned_directly(self):
        """Result with no AuthenticationResult is returned without calling update_tokens."""
        s = _make_stub()
        plain = {"ChallengeName": "SOMETHING_ELSE"}
        s.auth.sms_2fa.return_value = plain
        result = await s.sms2fa("123456", {})
        assert result == plain
        # Tokens must be untouched
        assert s.tokens.token_data["token"] == ""


# ---------------------------------------------------------------------------
# _retry_login
# ---------------------------------------------------------------------------


class TestRetryLogin:
    """Tests for SessionAuthMixin._retry_login()."""

    async def test_successful_retry_without_sms_challenge_completes(self):
        """login() returns AUTH_RESULT (no SMS challenge) — _retry_login completes."""
        s = _make_stub()
        s.auth.login.return_value = AUTH_RESULT
        # Should not raise
        await s._retry_login()

    async def test_sms_challenge_from_login_raises_reauth(self):
        """login() returning SMS_MFA challenge causes _retry_login to raise HiveReauthRequired."""
        s = _make_stub()
        s.auth.login.return_value = {"ChallengeName": "SMS_MFA"}
        with pytest.raises(HiveReauthRequired):
            await s._retry_login()

    async def test_invalid_username_converted_to_reauth(self):
        """HiveInvalidUsername from login() is converted to HiveReauthRequired."""
        s = _make_stub()
        s.auth.login.side_effect = HiveInvalidUsername()
        with pytest.raises(HiveReauthRequired):
            await s._retry_login()

    async def test_invalid_password_converted_to_reauth(self):
        """HiveInvalidPassword from login() is converted to HiveReauthRequired."""
        from apyhiveapi.helper.hive_exceptions import HiveInvalidPassword

        s = _make_stub()
        s.auth.login.side_effect = HiveInvalidPassword()
        with pytest.raises(HiveReauthRequired):
            await s._retry_login()


# ---------------------------------------------------------------------------
# hive_refresh_tokens — extra branches
# ---------------------------------------------------------------------------


class TestHiveRefreshTokensExtended:
    """Tests for hive_refresh_tokens branches not covered by the main test file."""

    async def test_file_mode_skips_refresh_entirely(self):
        """config.file=True skips all token-refresh logic; refresh_token never called."""
        s = _make_stub()
        s.config.file = True
        # Token is expired — would normally trigger refresh
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        result = await s.hive_refresh_tokens()
        assert result is None
        s.auth.refresh_token.assert_not_called()

    async def test_not_expired_and_no_force_refresh_returns_none_immediately(self):
        """Token not at threshold with force_refresh=False returns None without entering lock."""
        s = _make_stub()
        s.tokens.token_created = datetime.now()
        s.tokens.token_expiry = timedelta(hours=1)
        result = await s.hive_refresh_tokens(force_refresh=False)
        assert result is None
        s.auth.refresh_token.assert_not_called()

    async def test_lock_recheck_shows_fresh_returns_early_without_calling_refresh(self):
        """After acquiring lock, if token is now fresh and force_refresh=False, return early."""
        s = _make_stub()
        # Make token appear expired so we enter the lock
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)

        # Acquire lock in the foreground; start hive_refresh_tokens as a task that will block
        await s._refresh_lock.acquire()

        async def _release_after_refresh():
            """Refresh token state then release lock."""
            # Yield so hive_refresh_tokens can start and block on the lock
            await asyncio.sleep(0)
            # Make token appear fresh before the lock is released
            s.tokens.token_created = datetime.now()
            s.tokens.token_expiry = timedelta(hours=1)
            s._refresh_lock.release()

        release_task = asyncio.create_task(_release_after_refresh())
        result = await s.hive_refresh_tokens(force_refresh=False)
        await release_task

        # The re-check inside the lock found a fresh token — refresh_token must not be called
        s.auth.refresh_token.assert_not_called()
        assert result is None

    async def test_failed_to_refresh_falls_back_to_retry_login(self):
        """HiveFailedToRefreshTokens triggers _retry_login (force_refresh=False)."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.side_effect = HiveFailedToRefreshTokens()
        s._retry_login = AsyncMock()
        await s.hive_refresh_tokens(force_refresh=False)
        s._retry_login.assert_called_once()

    async def test_failed_to_refresh_with_force_refresh_raises_reauth(self):
        """HiveFailedToRefreshTokens with force_refresh=True raises HiveReauthRequired."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.side_effect = HiveFailedToRefreshTokens()
        with pytest.raises(HiveReauthRequired):
            await s.hive_refresh_tokens(force_refresh=True)

    async def test_api_error_during_refresh_reraises(self):
        """HiveApiError during refresh_token propagates to the caller."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.side_effect = HiveApiError()
        with pytest.raises(HiveApiError):
            await s.hive_refresh_tokens()

    async def test_successful_refresh_updates_tokens_and_logs_new_expiry(self):
        """Successful refresh (has AuthenticationResult) calls update_tokens."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.return_value = AUTH_RESULT
        await s.hive_refresh_tokens()
        assert s.tokens.token_data["token"] == "id-tok"
        assert s.tokens.token_data["accessToken"] == "acc-tok"

    async def test_force_refresh_enters_lock_even_when_token_is_fresh(self):
        """force_refresh=True bypasses the expiry pre-check and calls refresh_token."""
        s = _make_stub()
        # Token is fresh — would normally skip entirely
        s.tokens.token_created = datetime.now()
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.return_value = AUTH_RESULT
        await s.hive_refresh_tokens(force_refresh=True)
        s.auth.refresh_token.assert_called_once()


# ---------------------------------------------------------------------------
# update_tokens — elif "token" branch missing token_created and bare refreshToken
# ---------------------------------------------------------------------------


class TestUpdateTokensTokenBranch:
    """update_tokens must set token_created and guard missing refreshToken in elif branch."""

    async def test_token_branch_sets_token_created(self):
        """elif 'token' branch must update token_created (was missing, stayed datetime.min)."""
        s = _make_stub()
        await s.update_tokens(
            {"token": "id-tok", "refreshToken": "ref-tok", "accessToken": "acc-tok"}
        )
        assert s.tokens.token_created > datetime.min

    async def test_token_branch_updates_token_data(self):
        """elif 'token' branch stores all three token values."""
        s = _make_stub()
        await s.update_tokens(
            {"token": "id", "refreshToken": "ref", "accessToken": "acc"}
        )
        assert s.tokens.token_data["token"] == "id"
        assert s.tokens.token_data["refreshToken"] == "ref"
        assert s.tokens.token_data["accessToken"] == "acc"

    async def test_token_branch_missing_refresh_token_does_not_crash(self):
        """elif 'token' branch without refreshToken key must not raise KeyError."""
        s = _make_stub()
        await s.update_tokens({"token": "id", "accessToken": "acc"})
        assert s.tokens.token_data["token"] == "id"

    async def test_token_branch_update_expiry_false_does_not_update_token_created(self):
        """update_expiry_time=False skips the token_created assignment in elif 'token' branch."""

        s = _make_stub()
        original_created = s.tokens.token_created
        await s.update_tokens(
            {"token": "id", "accessToken": "acc"},
            update_expiry_time=False,
        )
        assert s.tokens.token_created == original_created


# ---------------------------------------------------------------------------
# hive_refresh_tokens — bare refreshToken access raises KeyError when missing
# ---------------------------------------------------------------------------


class TestHiveRefreshTokensMissingRefreshToken:
    """hive_refresh_tokens must not crash when token_data has no refreshToken."""

    async def test_missing_refresh_token_does_not_raise_key_error(self):
        """hive_refresh_tokens without refreshToken in token_data must not crash."""
        s = _make_stub()
        s.tokens.token_data = {"token": "id", "accessToken": "acc"}
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.return_value = None
        result = await s.hive_refresh_tokens()
        assert result is None


# ===========================================================================
# Migrated from test_remaining_branches.py
# ===========================================================================


class TestRetryWithBackoffNonZeroDelay:
    """Line 66: asyncio.sleep called when delay > 0."""

    async def test_non_zero_delay_is_awaited_but_succeeds(self):
        """A non-zero delay entry causes asyncio.sleep to be called; factory still runs."""
        from unittest.mock import patch

        s = _make_stub()
        calls = []

        async def factory():
            calls.append(1)
            return "ok"

        with patch(
            "apyhiveapi.session.auth.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await s._retry_with_backoff(factory, delays=(5,))
        assert result == "ok"
        mock_sleep.assert_called_once_with(5)
        assert len(calls) == 1

    async def test_zero_delay_does_not_call_sleep(self):
        """A zero delay skips asyncio.sleep."""
        from unittest.mock import patch

        s = _make_stub()

        async def factory():
            return "done"

        with patch(
            "apyhiveapi.session.auth.asyncio.sleep", new_callable=AsyncMock
        ) as mock_sleep:
            result = await s._retry_with_backoff(factory, delays=(0,))
        assert result == "done"
        mock_sleep.assert_not_called()


class TestUpdateTokensFlatDictWithExpiresIn:
    """Lines 100->106: flat token dict with ExpiresIn sets token_expiry."""

    async def test_flat_dict_with_expires_in_sets_token_expiry(self):
        """Flat token dict containing ExpiresIn updates tokens.token_expiry."""
        s = _make_stub()
        flat = {
            "token": "t",
            "refreshToken": "r",
            "accessToken": "a",
            "ExpiresIn": 1800,
        }
        await s.update_tokens(flat)
        assert s.tokens.token_expiry == timedelta(seconds=1800)

    async def test_flat_dict_tokens_are_stored(self):
        """All token values from flat dict are written to token_data."""
        s = _make_stub()
        flat = {"token": "my-id", "refreshToken": "my-rt", "accessToken": "my-at"}
        await s.update_tokens(flat)
        assert s.tokens.token_data["token"] == "my-id"
        assert s.tokens.token_data["refreshToken"] == "my-rt"
        assert s.tokens.token_data["accessToken"] == "my-at"


class TestLoginApiError:
    """Lines 160-162: HiveApiError in login() is logged and re-raised."""

    async def test_login_api_error_reraises(self):
        """HiveApiError raised by auth.login propagates unchanged to the caller."""
        s = _make_stub()
        s.auth.login.side_effect = HiveApiError()
        with pytest.raises(HiveApiError):
            await s.login()


class TestHiveRefreshTokensNoAuthResult:
    """Lines 341->373: refresh returns a result but without AuthenticationResult."""

    async def test_result_without_auth_result_does_not_update_tokens(self):
        """When refresh_token returns a dict with no AuthenticationResult, tokens stay unchanged."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        # Return something truthy but without AuthenticationResult
        s.auth.refresh_token.return_value = {"SomeOtherKey": "value"}
        result = await s.hive_refresh_tokens()
        # Tokens must not have been updated
        assert s.tokens.token_data["token"] == ""
        assert s.tokens.token_data["accessToken"] == ""
        # result is what refresh_token returned
        assert result == {"SomeOtherKey": "value"}

    async def test_none_refresh_result_does_not_update_tokens(self):
        """When refresh_token returns None, tokens are left unchanged."""
        s = _make_stub()
        s.tokens.token_created = datetime.now() - timedelta(hours=2)
        s.tokens.token_expiry = timedelta(hours=1)
        s.auth.refresh_token.return_value = None
        await s.hive_refresh_tokens()
        assert s.tokens.token_data["token"] == ""


class TestUpdateTokensUnknownKey:
    """session/auth.py 100->106: tokens dict has neither AuthenticationResult nor token."""

    async def test_unknown_key_does_not_raise_and_does_not_update_tokens(self):
        """When neither expected key is present, data stays {}, ExpiresIn check skips."""
        s = _make_stub()
        original_token = s.tokens.token_data["token"]
        # Pass a dict that is neither the AuthResult form nor the flat-token form
        await s.update_tokens({"some_other_key": "some_value"})
        # Tokens must be unchanged
        assert s.tokens.token_data["token"] == original_token

    async def test_unknown_key_does_not_set_token_expiry(self):
        """ExpiresIn check at line 106 skips when data is {} (no match in either branch)."""
        s = _make_stub()
        original_expiry = s.tokens.token_expiry
        await s.update_tokens({"random_key": "random_value"})
        assert s.tokens.token_expiry == original_expiry
