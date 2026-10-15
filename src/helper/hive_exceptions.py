"""Hive exception class."""

# pylint: skip-file


class FileInUse(Exception):
    """File in use exception.

    Args:
        Exception (object): Exception object to invoke
    """


class NoApiToken(Exception):
    """No API token exception.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveError(Exception):
    """Common base class for all Hive-specific exceptions.

    Args:
        Exception (object): Exception object to invoke
    """


class HiveApiError(HiveError):
    """Api error.

    Args:
        HiveError (object): Parent Hive error class
    """


class HiveAuthError(HiveApiError):
    """Auth error (401/403) — token may be expired or invalid.

    Args:
        HiveApiError (object): Parent API error class
    """


class HiveRefreshTokenExpired(HiveApiError):
    """Refresh token expired.

    Args:
        HiveApiError (object): Parent API error class
    """


class HiveFailedToRefreshTokens(HiveApiError):
    """Raise invalid refresh tokens.

    Args:
        HiveApiError (object): Parent API error class
    """


class HiveConnectionError(HiveApiError):
    """Hive could not be reached (timeout or network error).

    The failure is expected to be transient, so callers can retry.

    Args:
        HiveApiError (object): Parent API error class
    """


class HiveConfigurationError(HiveError):
    """Base class for configuration-related errors.

    Args:
        HiveError (object): Parent Hive error class
    """


class HiveUnknownConfiguration(HiveConfigurationError):
    """Unknown Hive Configuration.

    Args:
        HiveConfigurationError (object): Parent configuration error class
    """


class HiveInvalidDeviceAuthentication(HiveConfigurationError):
    """Raise invalid device authentication.

    Args:
        HiveConfigurationError (object): Parent configuration error class
    """


class HiveAuthCredentialError(HiveError):
    """Base class for authentication credential errors.

    Args:
        HiveError (object): Parent Hive error class
    """


class HiveInvalidUsername(HiveAuthCredentialError):
    """Raise invalid Username.

    Args:
        HiveAuthCredentialError (object): Parent credential error class
    """


class HiveInvalidPassword(HiveAuthCredentialError):
    """Raise invalid password.

    Args:
        HiveAuthCredentialError (object): Parent credential error class
    """


class HiveInvalid2FACode(HiveAuthCredentialError):
    """Raise invalid 2FA code.

    Args:
        HiveAuthCredentialError (object): Parent credential error class
    """


class HiveReauthRequired(HiveError):
    """Re-Authentication is required.

    Args:
        HiveError (object): Parent Hive error class
    """
