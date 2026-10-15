"""Backwards-compatible shim — use apyhiveapi.devices.plug instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.plug is deprecated; import from apyhiveapi.devices.plug",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.plug import HiveSmartPlug, Switch

__all__ = ["HiveSmartPlug", "Switch"]
