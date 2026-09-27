"""Unit tests for the hive_exceptions hierarchy."""

import pytest
from apyhiveapi.helper.hive_exceptions import (
    FileInUse,
    HiveApiError,
    HiveAuthCredentialError,
    HiveAuthError,
    HiveConfigurationError,
    HiveConnectionError,
    HiveError,
    HiveFailedToRefreshTokens,
    HiveInvalid2FACode,
    HiveInvalidDeviceAuthentication,
    HiveInvalidPassword,
    HiveInvalidUsername,
    HiveReauthRequired,
    HiveRefreshTokenExpired,
    HiveUnknownConfiguration,
    NoApiToken,
)


class TestHiveErrorBase:
    def test_hive_api_error_is_hive_error(self):
        assert issubclass(HiveApiError, HiveError)

    def test_hive_auth_error_is_hive_api_error(self):
        assert issubclass(HiveAuthError, HiveApiError)

    def test_hive_auth_error_is_hive_error(self):
        assert issubclass(HiveAuthError, HiveError)

    def test_hive_refresh_token_expired_is_hive_api_error(self):
        assert issubclass(HiveRefreshTokenExpired, HiveApiError)

    def test_hive_failed_to_refresh_is_hive_api_error(self):
        assert issubclass(HiveFailedToRefreshTokens, HiveApiError)

    def test_hive_connection_error_is_hive_api_error(self):
        # Existing `except HiveApiError` handlers keep catching it.
        assert issubclass(HiveConnectionError, HiveApiError)

    def test_hive_reauth_required_is_hive_error(self):
        assert issubclass(HiveReauthRequired, HiveError)


class TestCredentialErrors:
    def test_invalid_username_is_hive_auth_credential_error(self):
        assert issubclass(HiveInvalidUsername, HiveAuthCredentialError)

    def test_invalid_password_is_hive_auth_credential_error(self):
        assert issubclass(HiveInvalidPassword, HiveAuthCredentialError)

    def test_invalid_2fa_is_hive_auth_credential_error(self):
        assert issubclass(HiveInvalid2FACode, HiveAuthCredentialError)

    def test_auth_credential_error_is_hive_error(self):
        assert issubclass(HiveAuthCredentialError, HiveError)


class TestConfigurationErrors:
    def test_unknown_config_is_hive_configuration_error(self):
        assert issubclass(HiveUnknownConfiguration, HiveConfigurationError)

    def test_invalid_device_auth_is_hive_configuration_error(self):
        assert issubclass(HiveInvalidDeviceAuthentication, HiveConfigurationError)

    def test_configuration_error_is_hive_error(self):
        assert issubclass(HiveConfigurationError, HiveError)


class TestStandaloneExceptions:
    def test_file_in_use_is_not_hive_error(self):
        assert not issubclass(FileInUse, HiveError)

    def test_no_api_token_is_not_hive_error(self):
        assert not issubclass(NoApiToken, HiveError)

    def test_file_in_use_is_exception(self):
        assert issubclass(FileInUse, Exception)

    def test_no_api_token_is_exception(self):
        assert issubclass(NoApiToken, Exception)


class TestInstantiable:
    def test_hive_error_is_raiseable(self):
        with pytest.raises(HiveError):
            raise HiveError("test")

    def test_hive_api_error_caught_as_hive_error(self):
        with pytest.raises(HiveError):
            raise HiveApiError("test")

    def test_invalid_username_caught_as_hive_error(self):
        with pytest.raises(HiveError):
            raise HiveInvalidUsername("test")
