"""Backwards-compatible shim — use apyhiveapi.devices.sensor instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.sensor is deprecated; import from apyhiveapi.devices.sensor",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.sensor import HiveSensor, Sensor

__all__ = ["HiveSensor", "Sensor"]
