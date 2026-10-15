"""Backwards-compatible shim — use apyhiveapi.devices.action instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.action is deprecated; import from apyhiveapi.devices.action",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.action import HiveAction

__all__ = ["HiveAction"]
