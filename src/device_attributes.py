"""Backwards-compatible shim — use apyhiveapi.helper.device_attributes instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.device_attributes is deprecated; import from apyhiveapi.helper.device_attributes",
    DeprecationWarning,
    stacklevel=2,
)

from .helper.device_attributes import HiveAttributes

__all__ = ["HiveAttributes"]
