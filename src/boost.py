"""Backwards-compatible shim — use apyhiveapi.devices.boost instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.boost is deprecated; import from apyhiveapi.devices.boost",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.boost import BoostMixin

__all__ = ["BoostMixin"]
