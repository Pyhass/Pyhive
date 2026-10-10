"""Backwards-compatible shim — use apyhiveapi.session.polling instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.session_polling is deprecated; import from apyhiveapi.session.polling",
    DeprecationWarning,
    stacklevel=2,
)

from .session.polling import PollingMixin

__all__ = ["PollingMixin"]
