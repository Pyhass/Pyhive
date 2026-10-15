"""Backwards-compatible shim — use apyhiveapi.session.discovery instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.session_discovery is deprecated; import from apyhiveapi.session.discovery",
    DeprecationWarning,
    stacklevel=2,
)

from .session.discovery import DiscoveryMixin

__all__ = ["DiscoveryMixin"]
