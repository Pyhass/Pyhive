"""Device registration and management mixin for HiveAuthAsync."""

from __future__ import annotations

import base64
import datetime
import functools
import hashlib
import hmac
import logging
import os
import re
import socket
from typing import Any

import botocore

from ..helper.hive_exceptions import HiveApiError, HiveInvalid2FACode
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


class DeviceRegistrationMixin:
    """Device registration, confirmation, and management methods.

    Expects ``self.client``, ``self.loop``, ``self._client_id``,
    ``self.access_token``, ``self.device_group_key``, ``self.device_key``,
    ``self.device_password``, ``self.k``, ``self.g_value``, ``self.big_n``,
    ``self.small_a_value``, ``self.large_a_value``, and ``self.client_secret``
    to be set up by the owning class's ``__init__`` / ``async_init``.
    """

    # Attributes provided by HiveAuthAsync.__init__ / async_init
    client: Any
    loop: Any
    _client_id: str | None
    access_token: str | None
    device_group_key: str | None
    device_key: str | None
    device_password: str | None
    k: int
    g_value: int
    big_n: int
    small_a_value: int
    large_a_value: int
    client_secret: str | None

    def generate_hash_device(self, device_group_key, device_key):
        """Generate device hash key."""
        # source: https://github.com/amazon-archives/amazon-cognito-identity-js/blob/6b87f1a30a998072b4d98facb49dcaf8780d15b0/src/AuthenticationHelper.js#L137 # pylint: disable=line-too-long

        device_password = base64.standard_b64encode(os.urandom(40)).decode("utf-8")
        combined_string = f"{device_group_key}{device_key}:{device_password}"
        combined_string_hash = hash_sha256(combined_string.encode("utf-8"))
        salt = pad_hex(get_random(16))

        x_value = hex_to_long(hex_hash(salt + combined_string_hash))
        g_value = hex_to_long(G_HEX)
        big_n = hex_to_long(N_HEX)
        verifier_device_not_padded = pow(g_value, x_value, big_n)
        verifier = pad_hex(verifier_device_not_padded)

        device_secret_verifier_config = {
            "PasswordVerifier": base64.standard_b64encode(
                bytearray.fromhex(verifier)
            ).decode("utf-8"),
            "Salt": base64.standard_b64encode(bytearray.fromhex(salt)).decode("utf-8"),
        }
        self.device_password = device_password
        return device_secret_verifier_config

    def get_device_authentication_key(  # pylint: disable=too-many-positional-arguments
        self, device_group_key, device_key, device_password, server_b_value, salt
    ):
        """Get device authentication key."""
        u_value = calculate_u(self.large_a_value, server_b_value)
        if u_value == 0:
            raise ValueError("U cannot be zero.")
        username_password = f"{device_group_key}{device_key}:{device_password}"
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

    async def process_device_challenge(self, challenge_parameters):
        """Process device challenge."""
        username = challenge_parameters["USERNAME"]
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
        hkdf = self.get_device_authentication_key(
            self.device_group_key,
            self.device_key,
            self.device_password,
            hex_to_long(srp_b_hex),
            salt_hex,
        )
        secret_block_bytes = base64.standard_b64decode(secret_block_b64)
        msg = (
            bytearray(self.device_group_key, "utf-8")
            + bytearray(self.device_key, "utf-8")
            + bytearray(secret_block_bytes)
            + bytearray(timestamp, "utf-8")
        )
        hmac_obj = hmac.new(hkdf, msg, digestmod=hashlib.sha256)
        signature_string = base64.standard_b64encode(hmac_obj.digest())
        response = {
            "TIMESTAMP": timestamp,
            "USERNAME": username,
            "PASSWORD_CLAIM_SECRET_BLOCK": secret_block_b64,
            "PASSWORD_CLAIM_SIGNATURE": signature_string.decode("utf-8"),
            "DEVICE_KEY": self.device_key,
        }
        if self.client_secret is not None:
            response.update(
                {
                    "SECRET_HASH": self.get_secret_hash(
                        username, self._client_id, self.client_secret
                    )
                }
            )
        return response

    async def device_registration(self, device_name: str | None = None):
        """Register device with Hive."""
        _LOGGER.debug("device_registration - Registering device with Hive.")
        await self.confirm_device(device_name)
        await self.update_device_status()

    async def confirm_device(self, device_name: str | None = None):
        """Confirm Hive Device."""
        if self.client is None:
            await self.async_init()  # type: ignore[attr-defined]

        if device_name is None:
            device_name = socket.gethostname()

        result = None
        try:
            device_secret_verifier_config = self.generate_hash_device(
                self.device_group_key, self.device_key
            )
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.confirm_device,
                    AccessToken=self.access_token,
                    DeviceKey=self.device_key,
                    DeviceName=device_name,
                    DeviceSecretVerifierConfig=device_secret_verifier_config,
                ),
            )
        except botocore.exceptions.ClientError as err:
            code = (err.response or {}).get("Error", {}).get("Code", "")
            if code == "CodeMismatchException":
                raise HiveInvalid2FACode from err
            raise HiveApiError from err
        except botocore.exceptions.EndpointConnectionError as err:
            raise HiveApiError from err

        return result

    async def update_device_status(self):
        """Update Device Hive."""
        if self.client is None:
            await self.async_init()  # type: ignore[attr-defined]
        result = None
        try:
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.update_device_status,
                    AccessToken=self.access_token,
                    DeviceKey=self.device_key,
                    DeviceRememberedStatus="remembered",
                ),
            )
        except botocore.exceptions.EndpointConnectionError as err:
            raise HiveApiError from err

        return result

    async def get_device_data(self):
        """Get key device information for device authentication.

        Returns:
            tuple: (device_group_key, device_key, device_password, token_created)
                token_created is a datetime marking when the current tokens were issued.
                Pass all four values as ``device_data`` in ``start_session`` config so the
                session can compute token expiry from the real issue time rather than epoch.
        """
        return (
            self.device_group_key,
            self.device_key,
            self.device_password,
            self.token_created,
        )

    async def is_device_registered(self, access_token=None, device_key=None):
        """Check if the current device is registered with Cognito.

        Args:
            access_token (str, optional): Access token. Defaults to self.access_token.
            device_key (str, optional): Device key. Defaults to self.device_key.

        Returns:
            bool: True if device is registered and remembered, False otherwise.

        Raises:
            HiveApiError: If unable to reach Cognito endpoint.
        """
        if self.client is None:
            await self.async_init()  # type: ignore[attr-defined]

        token = access_token or self.access_token
        key = device_key or self.device_key

        if not token or not key:
            _LOGGER.debug(
                "is_device_registered - Missing access token or device key, "
                "device not registered"
            )
            return False

        _LOGGER.debug(
            "is_device_registered - Checking device registration status for device: %s",
            key,
        )

        try:
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.get_device,
                    AccessToken=token,
                    DeviceKey=key,
                ),
            )

            if result and "Device" in result:
                device_status = result["Device"].get("DeviceAttributes", [])
                for attr in device_status:
                    if (
                        attr.get("Name") == "dev:device_remembered_status"
                        and attr.get("Value") == "remembered"
                    ):
                        _LOGGER.debug(
                            "is_device_registered - Device %s is registered and remembered",
                            key,
                        )
                        return True

                _LOGGER.debug(
                    "is_device_registered - Device %s is registered but not remembered",
                    key,
                )

        except botocore.exceptions.ClientError as err:
            error = (err.response or {}).get("Error", {})
            error_code = error.get("Code")
            error_message = error.get("Message", "")

            if error_code == "ResourceNotFoundException":
                _LOGGER.debug(
                    "is_device_registered - Device %s not found in Cognito", key
                )
            elif error_code == "NotAuthorizedException":
                _LOGGER.warning(
                    "is_device_registered - Not authorized to check device status: %s",
                    error_message,
                )
            else:
                _LOGGER.error(
                    "is_device_registered - Error checking device status: %s - %s",
                    error_code,
                    error_message,
                )

        except botocore.exceptions.EndpointConnectionError as err:
            _LOGGER.error(
                "is_device_registered - Cannot reach Cognito endpoint: %s", str(err)
            )
            raise HiveApiError from err

        return False

    async def forget_device(self, access_token, device_key):
        """Forget device registered with Hive."""
        if self.client is None:
            await self.async_init()  # type: ignore[attr-defined]
        result = None

        try:
            result = await self.loop.run_in_executor(
                None,
                functools.partial(
                    self.client.forget_device,
                    AccessToken=access_token,
                    DeviceKey=device_key,
                ),
            )
        except botocore.exceptions.ClientError as err:
            raise HiveApiError from err
        except botocore.exceptions.EndpointConnectionError as err:
            raise HiveApiError from err

        return result
