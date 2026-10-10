"""Backwards-compatible shim — use apyhiveapi.devices.heating instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.heating is deprecated; import from apyhiveapi.devices.heating",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.heating import Climate, HiveHeating

__all__ = ["HiveHeating", "Climate"]
