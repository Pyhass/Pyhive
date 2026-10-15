"""Backwards-compatible shim — use apyhiveapi.devices.light instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.light is deprecated; import from apyhiveapi.devices.light",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.light import HiveLight, Light

__all__ = ["HiveLight", "Light"]
