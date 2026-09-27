"""Backwards-compatible shim — use apyhiveapi.devices.hub instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.hub is deprecated; import from apyhiveapi.devices.hub",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.hub import HiveHub

__all__ = ["HiveHub"]
