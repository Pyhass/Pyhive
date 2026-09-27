"""Backwards-compatible shim — use apyhiveapi.devices.color instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.color is deprecated; import from apyhiveapi.devices.color",
    DeprecationWarning,
    stacklevel=2,
)

from .devices.color import LightColorHandler

__all__ = ["LightColorHandler"]
