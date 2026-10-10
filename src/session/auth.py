"""Session authentication lifecycle mixin for HiveSession."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from ..helper.hive_exceptions import (
    HiveApiError,
    HiveFailedToRefreshTokens,
    HiveInvalid2FACode,
    HiveInvalidPassword,
    HiveInvalidUsername,
    HiveReauthRequired,
    HiveRefreshTokenExpired,
    HiveUnknownConfiguration,
)

_LOGGER = logging.getLogger(__name__)


class SessionAuthMixin:
    """Session authentication lifecycle methods.

    Expects ``self.auth``, ``self.tokens``, ``self.config``, and
    ``self.helper`` to be set up by the owning class's ``__init__``.
    """

    # Attributes provided by HiveSession.__init__
    auth: Any
    tokens: Any
    config: Any
    helper: Any
    _refresh_threshold: float
    _refresh_lock: asyncio.Lock

    async def _retry_with_backoff(
        self,
        coro_factory,
        *,
        delays: tuple = (0, 5, 10),
        reraise_as=None,
        pass_through: tuple = (),
    ):
        """Retry an async operation with sequential delays.

        Args:
            coro_factory: Zero-argument callable returning a coroutine to attempt.
            delays: Seconds to wait before each attempt; the first (0) is immediate.
            reraise_as: Exception *type* to raise once all attempts are exhausted.
                        Defaults to the type of the last caught exception.
            pass_through: Exception types that bypass retrying and propagate
                          immediately to the caller.

        Returns:
            The result of the first successful ``coro_factory()`` call.

        Raises:
            reraise_as (or type of last error): When all retry attempts fail.
        """
        last_err = None
        for delay in delays:
            if delay:
                await asyncio.sleep(delay)
            try:
                return await coro_factory()
            except pass_through:
                raise
            except Exception as err:  # pylint: disable=broad-except
                last_err = err
        if reraise_as is not None:
            raise reraise_as() from last_err
        if last_err is not None:
            raise last_err
        raise RuntimeError("Retry attempts exhausted without capturing an error")

    async def update_tokens(self, tokens: dict, update_expiry_time: bool = True):
        """Update session tokens.

        Args:
            tokens (dict): Tokens from API response.
            update_expiry_time (Boolean): Should the refresh interval be updated

        Returns:
            dict: Parsed dictionary of tokens
        """
        data: dict = {}
        _LOGGER.debug(
            "update_tokens - Input tokens: %s", self.helper.sanitize_payload(tokens)
        )
        if "AuthenticationResult" in tokens:
            data = tokens.get("AuthenticationResult") or {}
            if "IdToken" in data:
                self.tokens.token_data.update({"token": data["IdToken"]})
            if "RefreshToken" in data:
                self.tokens.token_data.update({"refreshToken": data["RefreshToken"]})
            if "AccessToken" in data:
                self.tokens.token_data.update({"accessToken": data["AccessToken"]})
            if update_expiry_time:
                self.tokens.token_created = datetime.now()
        elif "token" in tokens:
            data = tokens
            self.tokens.token_data.update({"token": data["token"]})
            if "refreshToken" in data:
                self.tokens.token_data.update({"refreshToken": data["refreshToken"]})
            if "accessToken" in data:
                self.tokens.token_data.update({"accessToken": data["accessToken"]})
            if update_expiry_time:
                self.tokens.token_created = datetime.now()

        if "ExpiresIn" in data:
            self.tokens.token_expiry = timedelta(seconds=data["ExpiresIn"])

        _LOGGER.debug(
            "update_tokens — Final session tokens: IdToken: len=%d tail=…%s | "
            "AccessToken: len=%d tail=…%s | "
            "RefreshToken: %s | "
            "ExpiresIn: %s | token_created: %s | token_expiry: %s",
            len(self.tokens.token_data.get("token", "")),
            self.tokens.token_data.get("token", "")[-4:],
            len(self.tokens.token_data.get("accessToken", "")),
            self.tokens.token_data.get("accessToken", "")[-4:],
            (
                f"present (len={len(self.tokens.token_data.get('refreshToken', ''))}"
                f" tail=…{self.tokens.token_data.get('refreshToken', '')[-4:]})"
                if self.tokens.token_data.get("refreshToken")
                else "not present"
            ),
            data.get("ExpiresIn", "N/A"),
            self.tokens.token_created,
            self.tokens.token_expiry,
        )

        return self.tokens

    async def login(self):
        """Login to hive account with business logic routing.

        Business Rules:
        1) Login successfully - tokens returned, no device login or SMS2FA needed
        2) Check for device login or SMS challenges
        3) Direct flow to one of the two
        4) If device login, process ends but check if device is registered
        5) If SMS, follow on with device registration

        Raises:
            HiveUnknownConfiguration: Login information is unknown.

        Returns:
            dict: result of the authentication request.
        """
        result = None
        if not self.auth:
            raise HiveUnknownConfiguration

        _LOGGER.debug("login - Attempting login to Hive account.")
        try:
            result = await self.auth.login()
        except HiveInvalidUsername:
            _LOGGER.error("Login failed: invalid username.")
            raise
        except HiveInvalidPassword:
            _LOGGER.error("Login failed: invalid password.")
            raise
        except HiveApiError:
            _LOGGER.error("Login failed: API error or no internet connection.")
            raise

        # Rule 1: Login successful - tokens returned, no challenges needed
        if result and "AuthenticationResult" in result:
            auth_keys = list(result["AuthenticationResult"].keys())
            _LOGGER.debug(
                "login - Login successful — AuthenticationResult keys: %s", auth_keys
            )
            await self.update_tokens(result)
            return result

        # Rule 2 & 3: Check for device login or SMS challenges and route
        challenge_name = result.get("ChallengeName")
        _LOGGER.debug("login - Challenge detected: %s", challenge_name)

        if challenge_name == self.auth.DEVICE_VERIFIER_CHALLENGE:
            # Rule 4: Device login flow - check if device is registered
            _LOGGER.debug("login - Routing to device login flow")
            return await self._handle_device_login_challenge(result)
        if challenge_name == self.auth.SMS_MFA_CHALLENGE:
            # Rule 5: SMS flow - will need device registration after 2FA
            _LOGGER.debug("login - Routing to SMS 2FA flow (requires user input)")
            return result
        _LOGGER.error("login - Unsupported challenge: %s", challenge_name)
        raise HiveUnknownConfiguration

    async def _handle_device_login_challenge(self, _login_result):
        """Handle device login challenge.

        Args:
            _login_result (dict): Result from initial login with DEVICE_SRP_AUTH challenge.

        Returns:
            dict: Authentication result with tokens.

        Raises:
            HiveReauthRequired: If device login encounters SMS_MFA (device not remembered).
            HiveInvalidDeviceAuthentication: If device is not registered.
        """
        _LOGGER.debug("_handle_device_login_challenge - Processing device login")
        result = await self.auth.device_login()

        if result and result.get("ChallengeName") == self.auth.SMS_MFA_CHALLENGE:
            _LOGGER.error(
                "_handle_device_login_challenge - Device login failed: SMS MFA challenge detected. "
                "Device is not remembered by Cognito. User must reauthenticate."
            )
            raise HiveReauthRequired

        if result and "AuthenticationResult" in result:
            auth_keys = list(result["AuthenticationResult"].keys())
            _LOGGER.debug(
                "_handle_device_login_challenge - Device login successful"
                " — AuthenticationResult keys: %s",
                auth_keys,
            )
            await self.update_tokens(result)

        return result

    async def sms2fa(self, code, session):
        """Login to hive account with 2 factor authentication.

        After successful SMS 2FA, checks if device needs registration and
        handles it automatically (Rule 5).

        Raises:
            HiveUnknownConfiguration: Login information is unknown.

        Returns:
            dict: result of the authentication request with device data if registered.
        """
        result = None
        if not self.auth:
            _LOGGER.error("2FA failed: authentication not initialised.")
            raise HiveUnknownConfiguration

        _LOGGER.debug("sms_2fa - Submitting 2FA code.")
        try:
            result = await self.auth.sms_2fa(code, session)
        except HiveInvalid2FACode:
            _LOGGER.error("2FA failed: invalid code entered.")
            raise
        except HiveApiError:
            _LOGGER.error("2FA failed: API error or no internet connection.")
            raise

        if result and "AuthenticationResult" in result:
            auth_keys = list(result["AuthenticationResult"].keys())
            _LOGGER.debug(
                "sms_2fa - 2FA login successful — AuthenticationResult keys: %s",
                auth_keys,
            )
            await self.update_tokens(result)

        return result

    async def _retry_login(self):
        """Attempt login with retries and backoff.

        This is called when token refresh fails. It attempts to login again,
        which may succeed via device login or may require user interaction (SMS 2FA).

        Raises:
            HiveReauthRequired: User interaction required (SMS 2FA challenge),
                                 credentials invalid, or all retries exhausted.
            HiveApiError: API error or no internet connection.
        """

        async def _attempt():
            result = await self.login()
            if result and result.get("ChallengeName") == self.auth.SMS_MFA_CHALLENGE:
                _LOGGER.error(
                    "_retry_login - Login requires SMS 2FA. User must reauthenticate."
                )
                raise HiveReauthRequired
            return result

        try:
            await self._retry_with_backoff(
                _attempt,
                reraise_as=HiveReauthRequired,
                pass_through=(
                    HiveReauthRequired,
                    HiveInvalidUsername,
                    HiveInvalidPassword,
                ),
            )
        except (HiveInvalidUsername, HiveInvalidPassword) as exc:
            _LOGGER.error(
                "_retry_login - Login failed with invalid credentials,"
                " reauthentication required."
            )
            raise HiveReauthRequired from exc

    async def hive_refresh_tokens(self, force_refresh: bool = False):
        """Refresh Hive tokens.

        Args:
            force_refresh (bool): Whether to force a token refresh regardless of expiry.

        Returns:
            boolean: True/False if update was successful
        """
        result = None

        if not self.config.file:
            expiry_time = self.tokens.token_created + (
                self.tokens.token_expiry * self._refresh_threshold
            )
            _LOGGER.debug(
                "hive_refresh_tokens - Session token expiry time ( Current: %s | Expiry: %s)",
                datetime.now(),
                expiry_time,
            )
            if datetime.now() >= expiry_time or force_refresh:
                async with self._refresh_lock:
                    # Re-check after acquiring lock — another caller may have already refreshed
                    expiry_time = self.tokens.token_created + (
                        self.tokens.token_expiry * self._refresh_threshold
                    )
                    if datetime.now() < expiry_time and not force_refresh:
                        return result
                    actual_expiry = self.tokens.token_created + self.tokens.token_expiry
                    _LOGGER.debug(
                        "hive_refresh_tokens - Session Token created: %s | Actual expiry: %s | "
                        "Early refresh (×%s): %s | Now: %s | Force refresh: %s",
                        self.tokens.token_created,
                        actual_expiry,
                        self._refresh_threshold,
                        expiry_time,
                        datetime.now(),
                        force_refresh,
                    )
                    try:
                        result = await self.auth.refresh_token(
                            self.tokens.token_data.get("refreshToken")
                        )

                        if result and "AuthenticationResult" in result:
                            auth_keys = list(result["AuthenticationResult"].keys())
                            _LOGGER.debug(
                                "hive_refresh_tokens - Token refresh"
                                " — AuthenticationResult keys: %s",
                                auth_keys,
                            )
                            await self.update_tokens(result)
                            new_expiry = (
                                self.tokens.token_created + self.tokens.token_expiry
                            )
                            _LOGGER.debug(
                                "hive_refresh_tokens - Session Token refresh"
                                " successful. New expiry: %s",
                                new_expiry,
                            )
                    except (HiveRefreshTokenExpired, HiveFailedToRefreshTokens) as exc:
                        _LOGGER.warning(
                            "Session Token refresh failed (%s), falling back to login.",
                            type(exc).__name__,
                        )
                        if not force_refresh:
                            await self._retry_login()
                        else:
                            _LOGGER.error(
                                "Token refresh failed during retry attempt, giving up."
                            )
                            raise HiveReauthRequired from exc
                    except HiveApiError:
                        _LOGGER.error("API error during token refresh.")
                        raise

        return result
