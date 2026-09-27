"""Auth file for logging in."""

from __future__ import annotations

import asyncio
import base64
import datetime
import functools
import hashlib
import hmac
import logging
import re
from typing import Any

import boto3
import botocore

from ..helper.hive_exceptions import (
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
from .device_registration import DeviceRegistrationMixin
from .hive_api import HiveApi
from .srp_crypto import (
    G_HEX,
    N_HEX,
    calculate_u,
    compute_hkdf,
    get_random,
    hash_sha256,
    hex_hash,
    hex_to_long,
    long_to_hex,
    pad_hex,
)

_LOGGER = logging.getLogger(__name__)


class HiveAuthAsync(DeviceRegistrationMixin):
    """Async api to interface with hive auth."""

    NEW_PASSWORD_REQUIRED_CHALLENGE = "NEW_PASSWORD_REQUIRED"
    PASSWORD_VERIFIER_CHALLENGE = "PASSWORD_VERIFIER"
    SMS_MFA_CHALLENGE = "SMS_MFA"
    DEVICE_VERIFIER_CHALLENGE = "DEVICE_SRP_AUTH"
    DEVICE_PASSWORD_CHALLENGE = "DEVICE_PASSWORD_VERIFIER"

    def __init__(  # pylint: disable=too-many-positional-arguments  # noqa: PLR0913
        self,
        username: str,
        password: str,
        device_group_key: str | None = None,
        device_key: str | None = None,
        device_password: str | None = None,
        client_secret: str | None = None,
    ):
        """Initialise async auth."""
        self.loop: asyncio.AbstractEventLoop | None = None
        self.username = username
        self.password = password
        self.device_group_key: str | None = device_group_key
        self.device_key: str | None = device_key
        self.device_password: str | None = device_password
        self.access_token: str | None = None
        self.token_created: datetime.datetime | None = None
        self.api = HiveApi()
        self.user_id = "user_id"
        self.client_secret = client_secret
        self.big_n: int = hex_to_long(N_HEX)
        self.g_value: int = hex_to_long(G_HEX)
        self.k: int = hex_to_long(hex_hash(pad_hex(N_HEX) + pad_hex(G_HEX)))
        self.small_a_value: int = self.generate_random_small_a()
        self.large_a_value: int = self.calculate_a()
        self.use_file = bool(self.username == "use@file.com")
        self.file_response = {"AuthenticationResult": {"AccessToken": "file"}}
        # The below variables are initialized in the async_init function
        self.data: dict | None = None
        self._pool_id: str | None = None
        self._client_id: str | None = None
        self._region: str | None = None
        self.client: Any = None

    async def async_init(self):
        """Initialise async variables."""
        self.loop = asyncio.get_running_loop()
        self.data = await self.loop.run_in_executor(None, self.api.get_login_info)
        if not self.data:
            raise HiveUnknownConfiguration("SSO login page returned no data")
        self._pool_id = self.data.get("UPID")
        self._client_id = self.data.get("CLIID")
        region_raw = self.data.get("REGION")
        if not self._pool_id or not region_raw:
            raise HiveUnknownConfiguration(
                "SSO login page did not return required pool/region data"
            )
        self._region = region_raw.split("_")[0]
        # Cognito USER_SRP_AUTH does not use IAM credentials — boto3 requires non-None values.
        self.client = await self.loop.run_in_executor(
            None,
            functools.partial(
                boto3.client,
                "cognito-idp",
                self._region,
                aws_access_key_id="ACCESS_KEY",
                aws_secret_access_key="SECRET_KEY",
                aws_session_token="SESSION_TOKEN",
            ),
        )

    def _to_int(self, value):
        """Accepts int or hex string and returns int."""
        if isinstance(value, int):
            return value
        if isinstance(value, bytes):
            return int(value.hex(), 16)
        return int(str(value), 16)

    def generate_random_small_a(self):
        """
        Helper function to generate a random big integer.

        :return {Long integer} a random value.
        """
        random_long_int = get_random(128)
        return random_long_int % self.big_n

    def _new_srp_ephemeral(self) -> None:
        """Generate a fresh SRP client ephemeral (a, A) pair.

        SRP ephemerals must not be reused across handshakes, so this is
        called at the start of every authentication attempt.
        """
        self.small_a_value = self.generate_random_small_a()
        self.large_a_value = self.calculate_a()

    def _store_auth_result(self, result: dict) -> None:
        """Store tokens and any new device keys from an AuthenticationResult."""
        auth_result = result["AuthenticationResult"]
        self.access_token = auth_result["AccessToken"]
        self.token_created = datetime.datetime.now()
        if "NewDeviceMetadata" in auth_result:
            self.device_group_key = auth_result["NewDeviceMetadata"]["DeviceGroupKey"]
            self.device_key = auth_result["NewDeviceMetadata"]["DeviceKey"]
            _LOGGER.debug("Device keys stored successfully.")

    def calculate_a(self):
        """
        Calculate the client's public value A.

        :param {Long integer} a Randomly generated small A.
        :return {Long integer} Computed large A.
        """
        big_a = pow(self.g_value, self.small_a_value, self.big_n)
        # safety check
        if (big_a % self.big_n) == 0:
            raise ValueError("Safety check for A failed")
        return big_a

    def get_password_authentication_key(self, username, password, server_b_value, salt):
        """
        Calculates the final hkdf based on computed S value, \
            and computed U value and the key.

        :param {String} username Username.
        :param {String} password Password.
        :param {Long integer} server_b_value Server B value.
        :param {Long integer} salt Generated salt.
        :return {Buffer} Computed HKDF value.
        """
        server_b_value = self._to_int(server_b_value)
        u_value = calculate_u(self.large_a_value, server_b_value)
        if u_value == 0:
            raise ValueError("U cannot be zero.")
        if not self._pool_id or "_" not in self._pool_id:
            raise HiveUnknownConfiguration(f"Invalid pool ID format: {self._pool_id!r}")
        pool_id = self._pool_id.split("_")[1]
        username_password = f"{pool_id}{username}:{password}"
        username_password_hash = hash_sha256(username_password.encode("utf-8"))

        x_value = hex_to_long(hex_hash(pad_hex(salt) + username_password_hash))
        g_mod_pow_xn = pow(self.g_value, x_value, self.big_n)
        int_value2 = (server_b_value - self.k * g_mod_pow_xn) % self.big_n
        exp = self.small_a_value + u_value * x_value
        s_value = pow(int_value2, exp, self.big_n)
        hkdf = compute_hkdf(
            bytearray.fromhex(pad_hex(s_value)),
            bytearray.fromhex(pad_hex(long_to_hex(u_value))),
        )
        return hkdf

    async def get_auth_params(self, is_device_login=False):
        """Get auth params."""
        _LOGGER.debug("get_auth_params - Getting auth params")
        auth_params = {
            "USERNAME": self.username,
            "SRP_A": long_to_hex(self.large_a_value),
        }
        if self.client_secret is not None:
            auth_params.update(
                {
                    "SECRET_HASH": self.get_secret_hash(
                        self.username, self._client_id, self.client_secret
                    )
                }
            )

        if is_device_login:
            auth_params["DEVICE_KEY"] = self.device_key

        _LOGGER.debug("Auth params: %s", auth_params)
        return auth_params

    @staticmethod
    def get_secret_hash(username, client_id, client_secret):
        """Get secret hash."""
        message = bytearray(username + client_id, "utf-8")
        hmac_obj = hmac.new(bytearray(client_secret, "utf-8"), message, hashlib.sha256)
        return base64.standard_b64encode(hmac_obj.digest()).decode("utf-8")

    async def process_challenge(self, challenge_parameters):
        """Process auth challenge."""
        self.user_id = challenge_parameters["USER_ID_FOR_SRP"]
        salt_hex = (
            challenge_parameters["SALT"]
            if isinstance(challenge_parameters["SALT"], str)
            else pad_hex(challenge_parameters["SALT"])
        )
        srp_b_hex = challenge_parameters["SRP_B"]
        secret_block_b64 = challenge_parameters["SECRET_BLOCK"]
        # re strips leading zero from a day number (required by AWS Cognito)
        timestamp = re.sub(
            r" 0(\d) ",
            r" \1 ",
            datetime.datetime.now(datetime.timezone.utc).strftime(
                "%a %b %d %H:%M:%S UTC %Y"
            ),
        )
        hkdf = await self.loop.run_in_executor(
            None,
            self.get_password_authentication_key,
            self.user_id,
            self.password,
            srp_b_hex,
            salt_hex,
        )
        secret_block_bytes = base64.standard_b64decode(secret_block_b64)
        msg = (
            bytearray(self._pool_id.split("_")[1], "utf-8")
            + bytearray(self.user_id, "utf-8")
            + bytearray(secret_block_bytes)
            + bytearray(timestamp, "utf-8")
        )
        hmac_obj = hmac.new(hkdf, msg, digestmod=hashlib.sha256)
        signature_string = base64.standard_b64encode(hmac_obj.digest())
        response = {
            "TIMESTAMP": timestamp,
            "USERNAME": self.user_id,
            "PASSWORD_CLAIM_SECRET_BLOCK": secret_block_b64,
            "PASSWORD_CLAIM_SIGNATURE": signature_string.decode("utf-8"),
        }
        if self.client_secret is not None:
            response.update(
                {
                    "SECRET_HASH": self.get_secret_hash(
                        self.username, self._client_id, self.client_secret
                    )
                }
            )

        if self.device_key is not None:
            response.update({"DEVICE_KEY": self.device_key})

        return response

    async def login(self):  # noqa: PLR0912, PLR0915  # pylint: disable=too-many-statements
        """Login into a Hive account - handles initial SRP auth only."""
        if self.use_file:
            _LOGGER.debug("login - Using file-based authentication.")
            return self.file_response

        if self.client is None:
            await self.async_init()

        self._new_srp_ephemeral()
        auth_params = await self.get_auth_params()
        response = None
        result = None
        _LOGGER.debug("login - Initiating SRP auth with Cognito.")
        try:
            response = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.initiate_auth,
                    AuthFlow="USER_SRP_AUTH",
                    AuthParameters=auth_params,
                    ClientId=self._client_id,
                ),
            )
        except botocore.exceptions.ClientError as err:
            code = (err.response or {}).get("Error", {}).get("Code", "")
            if code == "UserNotFoundException":
                _LOGGER.error("Cognito auth failed: user not found.")
                raise HiveInvalidUsername from err
            _LOGGER.error("Cognito auth failed: %s", code)
            raise HiveApiError from err
        except botocore.exceptions.EndpointConnectionError as err:
            _LOGGER.error("Cognito auth failed: cannot reach endpoint.")
            raise HiveApiError from err

        if "AuthenticationResult" in response:
            _LOGGER.debug("login - Authenticated directly without a challenge.")
            self._store_auth_result(response)
            return response

        if response.get("ChallengeName") == self.PASSWORD_VERIFIER_CHALLENGE:
            _LOGGER.debug("login - Processing PASSWORD_VERIFIER challenge.")
            challenge_response = await self.process_challenge(
                response["ChallengeParameters"]
            )
            try:
                result = await self.loop.run_in_executor(
                    None,
                    functools.partial(
                        self.client.respond_to_auth_challenge,
                        ClientId=self._client_id,
                        ChallengeName=self.PASSWORD_VERIFIER_CHALLENGE,
                        ChallengeResponses=challenge_response,
                    ),
                )
            except botocore.exceptions.ClientError as err:
                code = (err.response or {}).get("Error", {}).get("Code", "")
                if code == "NotAuthorizedException":
                    _LOGGER.error("Cognito auth challenge failed: not authorised.")
                    raise HiveInvalidPassword from err
                if code == "ResourceNotFoundException":
                    _LOGGER.error(
                        "Cognito auth challenge failed: device resource not found."
                    )
                    raise HiveInvalidDeviceAuthentication from err
                _LOGGER.error("Cognito auth challenge failed: %s", code)
                raise HiveApiError from err
            except botocore.exceptions.EndpointConnectionError as err:
                _LOGGER.error("Cognito auth challenge failed: cannot reach endpoint.")
                raise HiveApiError from err

            _LOGGER.debug("login - SRP auth challenge completed successfully.")

            if "AuthenticationResult" in result:
                self._store_auth_result(result)

            return result

        challenge_name = response.get("ChallengeName")
        _LOGGER.error("Unsupported Cognito challenge: %s", challenge_name)
        raise NotImplementedError(f"The {challenge_name} challenge is not supported")

    async def device_login(self):
        """Perform device login - handles DEVICE_SRP_AUTH challenge.

        Returns:
            dict: Authentication result with tokens.
        """
        _LOGGER.debug("device_login - Starting device SRP authentication.")

        if self.client is None:
            await self.async_init()

        self._new_srp_ephemeral()
        auth_params = await self.get_auth_params(is_device_login=True)

        _LOGGER.debug("device_login - Processing DEVICE_SRP_AUTH challenge.")
        try:
            initial_result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.respond_to_auth_challenge,
                    ClientId=self._client_id,
                    ChallengeName=self.DEVICE_VERIFIER_CHALLENGE,
                    ChallengeResponses=auth_params,
                ),
            )

            device_challenge_response = await self.process_device_challenge(
                initial_result["ChallengeParameters"]
            )
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.respond_to_auth_challenge,
                    ClientId=self._client_id,
                    ChallengeName=self.DEVICE_PASSWORD_CHALLENGE,
                    ChallengeResponses=device_challenge_response,
                ),
            )
        except botocore.exceptions.ClientError as err:
            error_code = (err.response or {}).get("Error", {}).get("Code", "")
            if error_code in ("ResourceNotFoundException", "NotAuthorizedException"):
                _LOGGER.error(
                    "Device login failed: device not registered or not remembered (%s).",
                    error_code,
                )
                raise HiveInvalidDeviceAuthentication from err
            raise
        except botocore.exceptions.EndpointConnectionError as err:
            _LOGGER.error("Device login failed: cannot reach endpoint.")
            raise HiveApiError from err

        _LOGGER.debug("device_login - Device authentication completed successfully.")
        return result

    async def sms_2fa(self, entered_code, challenge_parameters):
        """Send sms code for auth."""
        session = challenge_parameters.get("Session")
        code = str(entered_code)
        result = None
        _LOGGER.debug("sms_2fa - Submitting SMS 2FA code to Cognito.")
        try:
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.respond_to_auth_challenge,
                    ClientId=self._client_id,
                    ChallengeName=self.SMS_MFA_CHALLENGE,
                    Session=session,
                    ChallengeResponses={
                        "SMS_MFA_CODE": code,
                        "USERNAME": self.user_id,
                    },
                ),
            )
            if result and "AuthenticationResult" in result:
                self._store_auth_result(result)
        except botocore.exceptions.ClientError as err:
            code = (err.response or {}).get("Error", {}).get("Code", "")
            if code in ("NotAuthorizedException", "CodeMismatchException"):
                _LOGGER.error("2FA code rejected by Cognito.")
                raise HiveInvalid2FACode from err
            _LOGGER.error("2FA failed: %s", code)
            raise HiveApiError from err
        except botocore.exceptions.EndpointConnectionError as err:
            _LOGGER.error("2FA failed: cannot reach Cognito endpoint.")
            raise HiveApiError from err

        _LOGGER.debug("sms_2fa - 2FA authentication completed successfully.")
        return result

    async def refresh_token(self, token):
        """Refresh Hive Tokens."""
        if self.client is None:
            await self.async_init()
        _LOGGER.debug("refresh_token - Requesting token refresh from Cognito.")
        result = None
        auth_params = {"REFRESH_TOKEN": token}
        if self.device_key is not None:
            auth_params = {
                "REFRESH_TOKEN": token,
                "DEVICE_KEY": self.device_key,
            }

        try:
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.initiate_auth,
                    ClientId=self._client_id,
                    AuthFlow="REFRESH_TOKEN_AUTH",
                    AuthParameters=auth_params,
                ),
            )
        except botocore.exceptions.ClientError as err:
            error = (err.response or {}).get("Error", {})
            error_code = error.get("Code")
            error_message = error.get("Message", "")
            if (
                error_code == "NotAuthorizedException"
                and "Invalid Refresh Token" in str(error_message)
            ):
                _LOGGER.warning("Refresh token is invalid or expired.")
                raise HiveRefreshTokenExpired from err

            _LOGGER.error(
                "refresh_token - Token refresh failed: %s - %s",
                error_code,
                error_message,
            )
            raise HiveFailedToRefreshTokens from err
        except botocore.exceptions.EndpointConnectionError as err:
            _LOGGER.error(
                "refresh_token - Token refresh failed: cannot reach Cognito endpoint."
            )
            raise HiveConnectionError from err

        _LOGGER.debug("refresh_token - Cognito token refresh completed successfully.")
        return result
