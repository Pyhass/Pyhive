"""Backwards-compatible shim — use apyhiveapi.devices.hotwater instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.hotwater is deprecated; import from apyhiveapi.devices.hotwater",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.hotwater import HiveHotwater, WaterHeater

__all__ = ["HiveHotwater", "WaterHeater"]
