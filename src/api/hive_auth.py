"""Sync version of HiveAuth."""

import base64
import binascii
import datetime
import hashlib
import hmac
import os
import re
import socket

import boto3
import botocore

from ..helper.hive_exceptions import (
    HiveApiError,
    HiveInvalid2FACode,
    HiveInvalidDeviceAuthentication,
    HiveInvalidPassword,
    HiveInvalidUsername,
    HiveReauthRequired,
)
from .hive_api import HiveApi

# https://github.com/aws/amazon-cognito-identity-js/blob/master/src/AuthenticationHelper.js#L22
N_HEX = (
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    + "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    + "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    + "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    + "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    + "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    + "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    + "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    + "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    + "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    + "15728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64"
    + "ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    + "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6B"
    + "F12FFA06D98A0864D87602733EC86A64521F2B18177B200C"
    + "BBE117577A615D6C770988C0BAD946E208E24FA074E5AB31"
    + "43DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF"
)
# https://github.com/aws/amazon-cognito-identity-js/blob/master/src/AuthenticationHelper.js#L49
G_HEX = "2"
INFO_BITS = bytearray("Caldera Derived Key", "utf-8")


class HiveAuth:
    """Sync Hive Auth.

    Raises:
        ValueError: [description]
        ValueError: [description]
        ValueError: [description]
        HiveInvalidUsername: [description]
        HiveApiError: [description]
        HiveInvalidPassword: [description]
        HiveApiError: [description]
        NotImplementedError: [description]
        HiveInvalid2FACode: [description]
        HiveApiError: [description]
        HiveApiError: [description]

    Returns:
        [type]: [description]
    """

    NEW_PASSWORD_REQUIRED_CHALLENGE = "NEW_PASSWORD_REQUIRED"
    PASSWORD_VERIFIER_CHALLENGE = "PASSWORD_VERIFIER"
    SMS_MFA_CHALLENGE = "SMS_MFA"
    DEVICE_VERIFIER_CHALLENGE = "DEVICE_SRP_AUTH"

    def __init__(  # pylint: disable=too-many-positional-arguments  # noqa: PLR0913
        self,
        username: str,
        password: str,
        device_group_key: str | None = None,
        device_key: str | None = None,
        device_password: str | None = None,
        pool_region: str | None = None,
        client_secret: str | None = None,
    ):
        """Initialise Sync Hive Auth.

        Args:
            username (str): [description]
            password (str): [description]
            pool_region (str, optional): [description]. Defaults to None.
            client_secret (str, optional): [description]. Defaults to None.

        Raises:
            ValueError: pool_region and client should not both be specified.
        """
        if pool_region is not None:
            raise ValueError(
                "pool_region and client should not both be specified "
                "(region should be passed to the boto3 client instead)"
            )

        self.username = username
        self.password = password
        self.device_group_key = device_group_key
        self.device_key = device_key
        self.device_password = device_password
        self.access_token = None
        self.user_id = "user_id"
        self.client_secret = client_secret
        self.big_n = hex_to_long(N_HEX)
        self.g_value = hex_to_long(G_HEX)
        self.k = hex_to_long(hex_hash("00" + N_HEX + "0" + G_HEX))
        self.small_a_value = self.generate_random_small_a()
        self.large_a_value = self.calculate_a()
        self.use_file = bool(self.username == "use@file.com")
        self.file_response = {"AuthenticationResult": {"AccessToken": "file"}}
        self.api = HiveApi()
        self.data = self.api.get_login_info()
        self._pool_id = self.data.get("UPID")
        self._client_id = self.data.get("CLIID")
        self._region = self.data.get("REGION").split("_")[0]
        self.client = boto3.client(
            "cognito-idp",
            self._region,
            aws_access_key_id="ACCESS_KEY",
            aws_secret_access_key="SECRET_KEY",
            aws_session_token="SESSION_TOKEN",
        )

    def generate_random_small_a(self):
        """Helper function to generate a random big integer.

        Returns:
            int: {Long integer} a random value.
        """
        random_long_int = get_random(128)
        return random_long_int % self.big_n

    def calculate_a(self):
        """Calculate the client's public value A = g^a%N with the generated random number.

        Raises:
            ValueError: Safety check for 0 value.

        Returns:
            int: {Long integer} Computed large A.
        """
        big_a = pow(self.g_value, self.small_a_value, self.big_n)
        # safety check
        if (big_a % self.big_n) == 0:
            raise ValueError("Safety check for A failed")
        return big_a

    def get_password_authentication_key(
        self, username: str, password: str, server_b_value: str, salt: str
    ):
        """
        Calculates the final hkdf based on computed S value, and computed U value and the key.

        :param {String} username Username.
        :param {String} password Password.
        :param {Long integer} server_b_value Server B value.
        :param {Long integer} salt Generated salt.
        :return {Buffer} Computed HKDF value.
        """
        server_b_long = hex_to_long(server_b_value)
        u_value = calculate_u(self.large_a_value, server_b_long)
        if u_value == 0:
            raise ValueError("U cannot be zero.")
        pool_id = self._pool_id.split("_")[1]  # type: ignore[union-attr]
        username_password = f"{pool_id}{username}:{password}"
        username_password_hash = hash_sha256(username_password.encode("utf-8"))

        x_value = hex_to_long(hex_hash(pad_hex(int(salt, 16)) + username_password_hash))
        g_mod_pow_xn = pow(self.g_value, x_value, self.big_n)
        int_value2 = server_b_long - self.k * g_mod_pow_xn
        s_value = pow(int_value2, self.small_a_value + u_value * x_value, self.big_n)
        hkdf = compute_hkdf(
            bytearray.fromhex(pad_hex(s_value)),
            bytearray.fromhex(pad_hex(long_to_hex(u_value))),
        )
        return hkdf

    def get_auth_params(self):
        """Get params."""
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
        return auth_params

    @staticmethod
    def get_secret_hash(username, client_id: str, client_secret: str):
        """Get secret hash."""
        message = bytearray(username + client_id, "utf-8")
        hmac_obj = hmac.new(bytearray(client_secret, "utf-8"), message, hashlib.sha256)
        return base64.standard_b64encode(hmac_obj.digest()).decode("utf-8")

    def generate_hash_device(self, device_group_key, device_key):
        """Generate the device hash."""
        # source: https://github.com/amazon-archives/amazon-cognito-identity-js/blob/6b87f1a30a998072b4d98facb49dcaf8780d15b0/src/AuthenticationHelper.js#L137 # pylint: disable=line-too-long

        # random device password, which will be used for DEVICE_SRP_AUTH flow
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
        return device_password, device_secret_verifier_config

    def get_device_authentication_key(  # pylint: disable=too-many-positional-arguments
        self, device_group_key, device_key, device_password, server_b_value, salt
    ):
        """Get the device authentication key."""
        u_value = calculate_u(self.large_a_value, server_b_value)
        if u_value == 0:
            raise ValueError("U cannot be zero.")
        username_password = f"{device_group_key}{device_key}:{device_password}"
        username_password_hash = hash_sha256(username_password.encode("utf-8"))

        x_value = hex_to_long(hex_hash(pad_hex(salt) + username_password_hash))
        g_mod_pow_xn = pow(self.g_value, x_value, self.big_n)
        int_value2 = server_b_value - self.k * g_mod_pow_xn
        s_value = pow(int_value2, self.small_a_value + u_value * x_value, self.big_n)
        hkdf = compute_hkdf(
            bytearray.fromhex(pad_hex(s_value)),
            bytearray.fromhex(pad_hex(long_to_hex(u_value))),
        )
        return hkdf

    def process_device_challenge(self, challenge_parameters):
        """Process the device challenge."""
        username = challenge_parameters["USERNAME"]
        salt_hex = challenge_parameters["SALT"]
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

    def process_challenge(self, challenge_parameters: dict):
        """Process 2FA challenge."""
        self.user_id = challenge_parameters["USER_ID_FOR_SRP"]
        salt_hex = challenge_parameters["SALT"]
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
        hkdf = self.get_password_authentication_key(
            self.user_id, self.password, srp_b_hex, salt_hex
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

        return response

    def login(self):  # noqa: PLR0912
        """Login into a Hive account."""
        if self.use_file:
            return self.file_response

        auth_params = self.get_auth_params()
        if self.device_key is not None:
            auth_params["DEVICE_KEY"] = self.device_key
        response = None
        result = None
        try:
            response = self.client.initiate_auth(
                AuthFlow="USER_SRP_AUTH",
                AuthParameters=auth_params,
                ClientId=self._client_id,
            )
        except botocore.exceptions.ClientError as err:
            if err.__class__.__name__ == "UserNotFoundException":
                raise HiveInvalidUsername from err
        except botocore.exceptions.EndpointConnectionError as err:
            if err.__class__.__name__ == "EndpointConnectionError":
                raise HiveApiError from err

        if response["ChallengeName"] == self.PASSWORD_VERIFIER_CHALLENGE:
            challenge_response = self.process_challenge(response["ChallengeParameters"])
            if self.device_key is not None:
                challenge_response["DEVICE_KEY"] = self.device_key

            try:
                result = self.client.respond_to_auth_challenge(
                    ClientId=self._client_id,
                    ChallengeName=self.PASSWORD_VERIFIER_CHALLENGE,
                    ChallengeResponses=challenge_response,
                )
            except botocore.exceptions.ClientError as err:
                if err.__class__.__name__ == "NotAuthorizedException":
                    raise HiveInvalidPassword from err
                if err.__class__.__name__ == "ResourceNotFoundException":
                    raise HiveInvalidDeviceAuthentication from err
            except botocore.exceptions.EndpointConnectionError as err:
                if err.__class__.__name__ == "EndpointConnectionError":
                    raise HiveApiError from err

            return result
        challenge_name = response["ChallengeName"]
        raise NotImplementedError(f"The {challenge_name} challenge is not supported")

    def device_login(self):
        """Perform device login instead."""
        login_result = self.login()

        if "AuthenticationResult" in login_result:
            # Login succeeded without a device challenge (e.g. device tracking
            # not enforced). Tokens are already valid, return them directly.
            return login_result

        auth_params = self.get_auth_params()
        auth_params["DEVICE_KEY"] = self.device_key

        if login_result.get("ChallengeName") == self.DEVICE_VERIFIER_CHALLENGE:
            try:
                initial_result = self.client.respond_to_auth_challenge(
                    ClientId=self._client_id,
                    ChallengeName=self.DEVICE_VERIFIER_CHALLENGE,
                    ChallengeResponses=auth_params,
                )

                device_challenge_response = self.process_device_challenge(
                    initial_result["ChallengeParameters"]
                )
                result = self.client.respond_to_auth_challenge(
                    ClientId=self._client_id,
                    ChallengeName="DEVICE_PASSWORD_VERIFIER",
                    ChallengeResponses=device_challenge_response,
                )
            except botocore.exceptions.EndpointConnectionError as err:
                if err.__class__.__name__ == "EndpointConnectionError":
                    raise HiveApiError from err
        elif login_result.get("ChallengeName") == self.SMS_MFA_CHALLENGE:
            # Account has 2FA enabled and device is not remembered by Cognito.
            # Automatic re-authentication is not possible without user interaction.
            raise HiveReauthRequired
        else:
            raise HiveInvalidDeviceAuthentication

        return result

    def sms_2fa(self, entered_code: str, challenge_parameters: dict):
        """Process 2FA sms verification."""
        session = challenge_parameters.get("Session")
        code = str(entered_code)
        result = None
        try:
            result = self.client.respond_to_auth_challenge(
                ClientId=self._client_id,
                ChallengeName=self.SMS_MFA_CHALLENGE,
                Session=session,
                ChallengeResponses={
                    "SMS_MFA_CODE": code,
                    "USERNAME": self.user_id,
                },
            )
            if "NewDeviceMetadata" in result["AuthenticationResult"]:
                self.access_token = result["AuthenticationResult"]["AccessToken"]
                self.device_group_key = result["AuthenticationResult"][
                    "NewDeviceMetadata"
                ]["DeviceGroupKey"]
                self.device_key = result["AuthenticationResult"]["NewDeviceMetadata"][
                    "DeviceKey"
                ]
        except botocore.exceptions.ClientError as err:
            if err.__class__.__name__ in (
                "NotAuthorizedException",
                "CodeMismatchException",
            ):
                raise HiveInvalid2FACode from err
        except botocore.exceptions.EndpointConnectionError as err:
            if err.__class__.__name__ == "EndpointConnectionError":
                raise HiveApiError from err

        return result

    def device_registration(self, device_name: str | None = None):
        """Register Device."""
        self.confirm_device(device_name)
        self.update_device_status()

    def confirm_device(
        self,
        device_name: str | None = None,
    ):
        """Confirm Device Hive."""
        result = None
        if device_name is None:
            device_name = socket.gethostname()
        try:
            device_password, device_secret_verifier_config = self.generate_hash_device(
                self.device_group_key, self.device_key
            )
            self.device_password = device_password
            result = (
                self.client.confirm_device(
                    AccessToken=self.access_token,
                    DeviceKey=self.device_key,
                    DeviceName=device_name,
                    DeviceSecretVerifierConfig=device_secret_verifier_config,
                ),
            )
        except botocore.exceptions.EndpointConnectionError as err:
            if err.__class__.__name__ == "EndpointConnectionError":
                raise HiveApiError from err

        return result

    def update_device_status(self):
        """Update Device Hive."""
        result = None
        try:
            result = (
                self.client.update_device_status(
                    AccessToken=self.access_token,
                    DeviceKey=self.device_key,
                    DeviceRememberedStatus="remembered",
                ),
            )
        except botocore.exceptions.EndpointConnectionError as err:
            if err.__class__.__name__ == "EndpointConnectionError":
                raise HiveApiError from err

        return result

    def get_device_data(self):
        """Get key device information to use device authentication."""
        return self.device_group_key, self.device_key, self.device_password

    def refresh_token(
        self,
        token: str,
    ):
        """Refresh Hive Tokens."""
        result = None
        auth_params: dict[str, str] = {"REFRESH_TOKEN": token}
        if self.device_key is not None:
            auth_params = {"REFRESH_TOKEN": token, "DEVICE_KEY": self.device_key}
        try:
            result = self.client.initiate_auth(
                ClientId=self._client_id,
                AuthFlow="REFRESH_TOKEN_AUTH",
                AuthParameters=auth_params,
            )
        except botocore.exceptions.EndpointConnectionError as err:
            if err.__class__.__name__ == "EndpointConnectionError":
                raise HiveApiError from err

        return result

    def forget_device(self, access_token, device_key):
        """Forget device registered with Hive."""
        result = None

        try:
            result = self.client.forget_device(
                AccessToken=access_token,
                DeviceKey=device_key,
            )

        except botocore.exceptions.ClientError as err:
            if err.__class__.__name__ == "NotAuthorizedException":
                raise HiveInvalid2FACode from err
        except botocore.exceptions.EndpointConnectionError as err:
            if err.__class__.__name__ == "ResourceNotFoundException":
                raise HiveApiError from err

        return result


def hex_to_long(hex_string: str) -> int:
    """Convert hex to long."""
    return int(hex_string, 16)


def get_random(nbytes: int) -> int:
    """Get random bytes."""
    random_hex = binascii.hexlify(os.urandom(nbytes))
    return hex_to_long(random_hex.decode())


def hash_sha256(buf):
    """Authentication Helper hash."""
    a_value = hashlib.sha256(buf).hexdigest()
    return (64 - len(a_value)) * "0" + a_value


def hex_hash(hex_string):
    """Convert hex to hash."""
    return hash_sha256(bytearray.fromhex(hex_string))


def calculate_u(big_a, big_b):
    """
    Calculate the client's value U which is the hash of A and B.

    :param {Long integer} big_a Large A value.
    :param {Long integer} big_b Server B value.
    :return {Long integer} Computed U value.
    """
    u_hex_hash = hex_hash(pad_hex(big_a) + pad_hex(big_b))
    return hex_to_long(u_hex_hash)


def long_to_hex(long_num):
    """Convert long number to hex."""
    return f"{long_num:x}"


def pad_hex(long_int):
    """
    Converts a Long integer (or hex string) to hex format padded with zeroes for hashing.

    :param {Long integer|String} long_int Number or string to pad.
    :return {String} Padded hex string.
    """
    if not isinstance(long_int, str):
        hash_str = long_to_hex(long_int)
    else:
        hash_str = long_int
    if len(hash_str) % 2 == 1:
        hash_str = f"0{hash_str}"
    elif hash_str[0] in "89ABCDEFabcdef":
        hash_str = f"00{hash_str}"
    return hash_str


def compute_hkdf(ikm, salt):
    """
    Standard hkdf algorithm.

    :param {Buffer} ikm Input key material.
    :param {Buffer} salt Salt value.
    :return {Buffer} Strong key material.
    @private
    """
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    info_bits_update = INFO_BITS + bytearray(chr(1), "utf-8")
    hmac_hash = hmac.new(prk, info_bits_update, hashlib.sha256).digest()
    return hmac_hash[:16]
