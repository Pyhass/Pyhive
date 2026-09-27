"""Verify a built distribution is importable and complete.

The test suite runs against ``src/`` via an editable install, so it cannot
catch packaging mistakes — a missing entry in ``[tool.setuptools] packages``
produces a wheel that installs cleanly and then fails at ``import``. This
script closes that gap by installing the built wheel into a throwaway
virtualenv and importing every module in every flavour.

Usage:
    python scripts/verify_dist.py [dist_dir]

Exits non-zero with a description of what is missing or unimportable.
"""

import json
import subprocess
import sys
import sysconfig
import tempfile
import venv
from pathlib import Path

# Flavours shipped by this distribution: the async original, its published
# alias, and the unasync-generated sync build.
FLAVOURS = ("apyhiveapi", "pyhive", "pyhiveapi")

# Subpackages that must be present in each flavour. Guards against the
# packages list in pyproject.toml drifting behind the source layout.
REQUIRED_SUBPACKAGES = ("api", "devices", "helper", "session")

# Package data that must ship alongside the async flavours.
REQUIRED_DATA = {"apyhiveapi": ["data/data.json"], "pyhive": ["data/data.json"]}

# Entry points the Home Assistant integration depends on. A build that
# imports but has lost these is still a broken release.
REQUIRED_ATTRS = {
    "apyhiveapi": ["API", "Auth", "Hive", "HiveReauthRequired"],
    "pyhive": ["API", "Auth", "Hive"],
    "pyhiveapi": ["API", "Auth", "Hive"],
}

# Runs inside the throwaway venv, so it must stay stdlib-only.
PROBE = """
import importlib
import importlib.util
import json
import pathlib
import pkgutil
import sys
import warnings

warnings.simplefilter("ignore", DeprecationWarning)

flavours = json.loads(sys.argv[1])
required_subpackages = json.loads(sys.argv[2])
required_data = json.loads(sys.argv[3])
required_attrs = json.loads(sys.argv[4])

failures = []
imported = 0

for flavour in flavours:
    try:
        top = importlib.import_module(flavour)
    except Exception as err:  # noqa: BLE001 - report, do not raise
        failures.append(f"{flavour}: cannot import: {err!r}")
        continue

    root = top.__path__[0]
    for sub in required_subpackages:
        if not importlib.util.find_spec(f"{flavour}.{sub}"):
            failures.append(f"{flavour}.{sub}: subpackage not shipped")

    for rel in required_data.get(flavour, []):
        if not (pathlib.Path(root) / rel).is_file():
            failures.append(f"{flavour}/{rel}: package data not shipped")

    for attr in required_attrs.get(flavour, []):
        if not hasattr(top, attr):
            failures.append(f"{flavour}.{attr}: missing from public API")

    for mod in pkgutil.walk_packages(top.__path__, flavour + "."):
        imported += 1
        try:
            importlib.import_module(mod.name)
        except Exception as err:  # noqa: BLE001 - report, do not raise
            failures.append(f"{mod.name}: {type(err).__name__}: {err}")

print(json.dumps({"imported": imported, "failures": failures}))
"""


def find_wheel(dist_dir: Path) -> Path:
    """Return the single wheel in ``dist_dir``.

    Args:
        dist_dir: Directory holding built distributions.

    Returns:
        Path to the wheel.

    Raises:
        SystemExit: No wheel, or more than one, was found.
    """
    wheels = sorted(dist_dir.glob("*.whl"))
    if not wheels:
        raise SystemExit(
            f"error: no wheel found in {dist_dir}/ — run `python -m build`"
        )
    if len(wheels) > 1:
        names = ", ".join(w.name for w in wheels)
        raise SystemExit(f"error: expected one wheel in {dist_dir}/, found: {names}")
    return wheels[0]


def main(argv: list[str]) -> int:
    """Install the built wheel in a clean venv and import everything in it.

    Args:
        argv: Command line arguments; ``argv[0]`` may be the dist directory.

    Returns:
        0 when the distribution is complete and importable, 1 otherwise.
    """
    dist_dir = Path(argv[0] if argv else "dist")
    wheel = find_wheel(dist_dir)
    print(f"verifying {wheel.name}")

    with tempfile.TemporaryDirectory() as tmp:
        env_dir = Path(tmp) / "venv"
        venv.create(env_dir, with_pip=True, clear=True)
        bin_dir = "Scripts" if sysconfig.get_platform().startswith("win") else "bin"
        python = env_dir / bin_dir / "python"

        install = subprocess.run(
            [str(python), "-m", "pip", "install", "--quiet", str(wheel)],
            capture_output=True,
            text=True,
            check=False,
        )
        if install.returncode != 0:
            print(install.stdout + install.stderr, file=sys.stderr)
            print("error: wheel failed to install", file=sys.stderr)
            return 1

        # Run from the temp dir so a sibling src/ tree cannot shadow the
        # installed package.
        probe = subprocess.run(
            [
                str(python),
                "-c",
                PROBE,
                json.dumps(FLAVOURS),
                json.dumps(REQUIRED_SUBPACKAGES),
                json.dumps(REQUIRED_DATA),
                json.dumps(REQUIRED_ATTRS),
            ],
            capture_output=True,
            text=True,
            cwd=tmp,
            check=False,
        )
        if probe.returncode != 0 or not probe.stdout.strip():
            print(probe.stdout + probe.stderr, file=sys.stderr)
            print("error: verification probe crashed", file=sys.stderr)
            return 1

        result = json.loads(probe.stdout)

    failures = result["failures"]
    print(f"imported {result['imported']} modules across {len(FLAVOURS)} flavours")
    if failures:
        print(f"\nerror: {len(failures)} problem(s) in the built distribution:")
        for failure in failures:
            print(f"  - {failure}")
        print(
            "\nIf a subpackage is missing, add it to `[tool.setuptools] packages` "
            "in pyproject.toml.",
        )
        return 1

    print("distribution is complete and importable")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
