"""E2E test: generate the pyhiveapi sync package via unasync and verify it works.

Strategy
--------
1. Copy the minimal async source files (``__init__.py``, ``api/hive_api.py``,
   ``api/hive_auth.py``) into ``tmp_path/apyhiveapi/`` — mirroring the path
   segment that unasync matches on.
2. Run ``unasync.unasync_files()`` with the same Rule set defined in
   ``setup.py``.  This rewrites the files into ``tmp_path/pyhiveapi/``,
   stripping ``async``/``await`` and replacing identifiers as configured.
3. Pre-populate ``sys.modules["pyhiveapi.helper.*"]`` and
   ``sys.modules["pyhiveapi.hive"]`` by aliasing the live ``apyhiveapi``
   equivalents — only the API layer differs between async and sync.
4. Prepend ``tmp_path`` to ``sys.path`` so Python finds the generated
   ``pyhiveapi`` package, then import it and assert that ``API`` is the
   synchronous ``HiveApi`` class (not ``HiveApiAsync``).
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest
import unasync

# ---------------------------------------------------------------------------
# Paths and rule constants matching setup.py
# ---------------------------------------------------------------------------

_SRC = Path(__file__).parent.parent.parent / "src"

_RULES = [
    unasync.Rule(
        "/apyhiveapi/",
        "/pyhiveapi/",
        additional_replacements={
            "apyhiveapi": "pyhiveapi",
            "asyncio": "threading",
        },
    ),
    unasync.Rule(
        "/apyhiveapi/api/",
        "/pyhiveapi/api/",
        additional_replacements={"apyhiveapi": "pyhiveapi"},
    ),
]


# ---------------------------------------------------------------------------
# Fixture: build the generated pyhiveapi package in a temp directory
# ---------------------------------------------------------------------------


@pytest.fixture()
def generated_pyhiveapi(tmp_path):
    """Copy minimal async sources, run unasync, yield the tmp dir."""
    async_root = tmp_path / "apyhiveapi"
    async_api = async_root / "api"
    async_api.mkdir(parents=True)

    # Copy only the files that form the sync API surface
    shutil.copy(_SRC / "__init__.py", async_root / "__init__.py")
    shutil.copy(_SRC / "api" / "__init__.py", async_api / "__init__.py")
    shutil.copy(_SRC / "api" / "hive_api.py", async_api / "hive_api.py")
    shutil.copy(_SRC / "api" / "hive_auth.py", async_api / "hive_auth.py")

    # Collect all copied Python files and apply the unasync rules
    source_files = [str(p) for p in async_root.rglob("*.py")]
    unasync.unasync_files(source_files, _RULES)

    yield tmp_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_apyhiveapi_helpers_loaded() -> None:
    """Import apyhiveapi helper modules so they appear in sys.modules for aliasing."""
    import apyhiveapi.helper.const  # noqa: F401  # pylint: disable=unused-import
    import apyhiveapi.helper.hive_exceptions  # noqa: F401  # pylint: disable=unused-import
    import apyhiveapi.hive  # noqa: F401  # pylint: disable=unused-import


def _alias_helpers_to_pyhiveapi(added_keys: list[str]) -> None:
    """Register apyhiveapi.helper.* and apyhiveapi.hive under pyhiveapi.* names.

    The generated pyhiveapi package's __init__.py imports from
    ``.helper.const`` and ``.helper.hive_exceptions`` and ``.hive``.  Those
    sub-modules are identical between async and sync flavours, so aliasing the
    already-imported apyhiveapi objects avoids having to transform and load the
    entire helper tree.
    """
    for key, mod in list(sys.modules.items()):
        if key in ("apyhiveapi.hive", "apyhiveapi.helper") or key.startswith(
            "apyhiveapi.helper."
        ):
            pyhive_key = "pyhiveapi" + key[len("apyhiveapi") :]
            if pyhive_key not in sys.modules:
                sys.modules[pyhive_key] = mod
                added_keys.append(pyhive_key)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSyncPackageGeneration:
    """Verify that the unasync transformation produces a working sync package."""

    def test_pyhiveapi_directory_is_created(self, generated_pyhiveapi):
        """unasync_files must write output files into pyhiveapi/."""
        pyhiveapi_dir = generated_pyhiveapi / "pyhiveapi"
        assert pyhiveapi_dir.is_dir(), (
            "unasync did not create pyhiveapi/ directory — check Rule fromdir/todir"
        )

    def test_init_py_is_generated(self, generated_pyhiveapi):
        """A __init__.py must be generated in the pyhiveapi package root."""
        init_file = generated_pyhiveapi / "pyhiveapi" / "__init__.py"
        assert init_file.is_file(), "pyhiveapi/__init__.py was not generated"

    def test_hive_api_py_is_generated(self, generated_pyhiveapi):
        """api/hive_api.py must be generated in pyhiveapi/api/."""
        api_file = generated_pyhiveapi / "pyhiveapi" / "api" / "hive_api.py"
        assert api_file.is_file(), "pyhiveapi/api/hive_api.py was not generated"

    def test_hive_auth_py_is_generated(self, generated_pyhiveapi):
        """api/hive_auth.py must be generated in pyhiveapi/api/."""
        auth_file = generated_pyhiveapi / "pyhiveapi" / "api" / "hive_auth.py"
        assert auth_file.is_file(), "pyhiveapi/api/hive_auth.py was not generated"

    def test_generated_init_contains_hiveapi_import(self, generated_pyhiveapi):
        """The generated __init__.py must reference HiveApi (sync class name)."""
        init_text = (generated_pyhiveapi / "pyhiveapi" / "__init__.py").read_text()
        assert "HiveApi" in init_text, (
            "pyhiveapi/__init__.py does not reference HiveApi — "
            "unasync token replacement may have failed"
        )

    def _import_generated_pyhiveapi(self, generated_pyhiveapi, monkeypatch):
        """Shared setup: generate helper aliases, clear stale modules, import."""
        _ensure_apyhiveapi_helpers_loaded()

        # Clear stale pyhiveapi entries FIRST so our fresh aliases aren't wiped
        stale = [
            k for k in sys.modules if k == "pyhiveapi" or k.startswith("pyhiveapi.")
        ]
        for key in stale:
            del sys.modules[key]

        # Now alias apyhiveapi.helper.* and apyhiveapi.hive under pyhiveapi.*
        injected: list[str] = []
        _alias_helpers_to_pyhiveapi(injected)

        monkeypatch.syspath_prepend(str(generated_pyhiveapi))

        import pyhiveapi as pkg  # noqa: PLC0415

        return pkg, injected

    def _cleanup_pyhiveapi(self, injected: list[str]) -> None:
        for key in injected:
            sys.modules.pop(key, None)
        for key in list(sys.modules):
            if key == "pyhiveapi" or key.startswith("pyhiveapi."):
                del sys.modules[key]

    def test_generated_api_is_sync_hive_api_class(
        self, generated_pyhiveapi, monkeypatch
    ):
        """Importing the generated pyhiveapi package exposes sync HiveApi as API."""
        injected: list[str] = []
        try:
            pkg, injected = self._import_generated_pyhiveapi(
                generated_pyhiveapi, monkeypatch
            )
            assert hasattr(pkg, "API"), "pyhiveapi.API is missing"
            assert "HiveApi" in pkg.API.__name__, (
                f"Expected sync HiveApi class but got {pkg.API.__name__!r}"
            )
        finally:
            self._cleanup_pyhiveapi(injected)

    def test_generated_auth_is_sync_hive_auth_class(
        self, generated_pyhiveapi, monkeypatch
    ):
        """Importing the generated pyhiveapi package exposes sync HiveAuth as Auth."""
        injected: list[str] = []
        try:
            pkg, injected = self._import_generated_pyhiveapi(
                generated_pyhiveapi, monkeypatch
            )
            assert hasattr(pkg, "Auth"), "pyhiveapi.Auth is missing"
            assert "HiveAuth" in pkg.Auth.__name__, (
                f"Expected sync HiveAuth class but got {pkg.Auth.__name__!r}"
            )
        finally:
            self._cleanup_pyhiveapi(injected)

    def test_async_keywords_stripped_from_generated_api(self, generated_pyhiveapi):
        """The generated hive_api.py must contain no 'async def' or 'await' keywords."""
        api_text = (
            generated_pyhiveapi / "pyhiveapi" / "api" / "hive_api.py"
        ).read_text()
        assert "async def" not in api_text, (
            "unasync did not strip 'async def' from hive_api.py"
        )
        assert " await " not in api_text, (
            "unasync did not strip 'await' from hive_api.py"
        )

    def test_apyhiveapi_identifier_replaced_in_generated_files(
        self, generated_pyhiveapi
    ):
        """The generated __init__.py must not contain the 'apyhiveapi' identifier."""
        init_text = (generated_pyhiveapi / "pyhiveapi" / "__init__.py").read_text()
        assert "apyhiveapi" not in init_text, (
            "unasync did not replace 'apyhiveapi' with 'pyhiveapi' in __init__.py"
        )
