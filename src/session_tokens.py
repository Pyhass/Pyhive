"""Backwards-compatible shim — use apyhiveapi.session.auth instead."""

# pylint: skip-file
# ruff: noqa: F401, E402
import warnings

warnings.warn(
    "apyhiveapi.session_tokens is deprecated; import from apyhiveapi.session.auth",
    DeprecationWarning,
    stacklevel=2,
)

from .session.auth import SessionAuthMixin as TokenMixin

__all__ = ["TokenMixin"]
