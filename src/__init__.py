"""__init__.py."""

# pylint: skip-file
# ruff: noqa
if __name__ == "pyhiveapi":  # pragma: no cover
    from .api.hive_api import HiveApi as API  # type: ignore[assignment]  # pragma: no cover
    from .api.hive_auth import HiveAuth as Auth  # type: ignore[assignment]  # pragma: no cover
else:
    from .api.hive_async_api import HiveApiAsync as API  # type: ignore[assignment]
    from .api.hive_auth_async import HiveAuthAsync as Auth  # type: ignore[assignment]

from .helper.const import SMS_REQUIRED
from .helper.hive_exceptions import (
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
)
from .hive import Hive
