"""Run a read-only Hive session in the background for local testing.

Starts a session against the bundled fixture (``--file``) or a real Hive
account (``--live``) as a background process that polls until it is stopped
(``--stop``), logging the shape of each product's state to ``logs/``.
It never calls a setter, so it cannot change any device.

Live mode asks for the password and SMS code at hidden/interactive prompts.
The password is never stored. After the first SMS login the device
credentials are saved in the macOS Keychain so later runs skip the SMS.

Live mode logs in in the foreground, then hands the session to the background
process over a pipe, so nothing sensitive is put on a command line.

The summary shows product types, shortened IDs, the mode and state key names
only. Library log lines are printed as the library emits them and can include
device names.
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from apyhiveapi import SMS_REQUIRED, Auth, Hive
from apyhiveapi.helper.hive_exceptions import HiveInvalidDeviceAuthentication

FILE_USERNAME = "use@file.com"
KEYCHAIN_SERVICE = "pyhive-dev"
KEYCHAIN_ACCOUNT = "live-session"
SHORT_ID_LENGTH = 8
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_MAX_BYTES = 5_000_000
LOG_BACKUPS = 2

LOG = logging.getLogger("run_session")


def _keychain_available() -> bool:
    return sys.platform == "darwin" and shutil.which("security") is not None


def load_stored() -> dict:
    """Return the stored username and device credentials, or an empty dict."""
    if not _keychain_available():
        return {}
    result = subprocess.run(
        [
            "security",
            "find-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
            "-w",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {}
    try:
        return json.loads(bytes.fromhex(result.stdout.strip()))
    except ValueError:
        return {}


def save_stored(username: str, device_data: list) -> bool:
    """Save the username and device credentials in the Keychain."""
    if not _keychain_available():
        return False
    value = json.dumps({"username": username, "device_data": device_data})
    # Sent on stdin (hex-encoded, so no quoting) to keep it off the process list.
    command = (
        f"add-generic-password -U -s {KEYCHAIN_SERVICE} -a {KEYCHAIN_ACCOUNT} "
        f"-w {value.encode().hex()}\n"
    )
    result = subprocess.run(
        ["security", "-i"],
        input=command,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def forget_stored() -> None:
    """Delete the stored username and device credentials."""
    if not _keychain_available():
        print("No Keychain on this platform - nothing is stored.")
        return
    result = subprocess.run(
        [
            "security",
            "delete-generic-password",
            "-s",
            KEYCHAIN_SERVICE,
            "-a",
            KEYCHAIN_ACCOUNT,
        ],
        capture_output=True,
        check=False,
    )
    print(
        "Stored credentials removed." if result.returncode == 0 else "Nothing stored."
    )


def _tokens(result: dict) -> dict:
    auth_result = result["AuthenticationResult"]
    return {
        "token": auth_result["IdToken"],
        "refreshToken": auth_result["RefreshToken"],
        "accessToken": auth_result["AccessToken"],
    }


async def live_config() -> dict:
    """Log in to a real Hive account and return the start_session config."""
    stored = load_stored()
    username = stored.get("username") or input("Hive email: ").strip()
    password = getpass.getpass("Hive password (hidden, not stored): ")
    device_data = stored.get("device_data")

    if device_data:
        print("Logging in with the stored device credentials (no SMS)...")
        auth = Auth(username, password, *device_data)
        try:
            result = await auth.device_login()
        except HiveInvalidDeviceAuthentication:
            sys.exit(
                "Hive rejected the stored device credentials. "
                "Run `make live-forget`, then try again."
            )
    else:
        print("Logging in...")
        auth = Auth(username, password)
        result = await auth.login()
        if result.get("ChallengeName") == SMS_REQUIRED:
            code = input("SMS code: ").strip()
            result = await auth.sms_2fa(code, result)
        device_data = list((await auth.get_device_data())[:3])
        if all(device_data) and save_stored(username, device_data):
            print("Device credentials saved in the macOS Keychain.")
        else:
            print("Device credentials not saved - the next run will need an SMS.")

    config = {"tokens": _tokens(result), "username": username, "password": password}
    if all(device_data):
        config["device_data"] = device_data
    return config


def install_drop(hive: Hive, keys: list[str], switch: dict) -> None:
    """Strip *keys* from every product's state while ``switch["on"]`` is set.

    Simulates the incomplete responses Hive occasionally returns.
    """

    def _strip(response):
        if switch["on"] and isinstance(response, dict):
            for product in (response.get("parsed") or {}).get("products", []):
                state = product.get("state")
                if isinstance(state, dict):
                    for key in keys:
                        state.pop(key, None)
        return response

    # Fixture sessions read through open_file, live sessions through get_all.
    open_file = hive.open_file
    get_all = hive.api.get_all

    async def _get_all():
        return _strip(await get_all())

    hive.open_file = lambda file: _strip(open_file(file))
    hive.api.get_all = _get_all


def log_summary(hive: Hive, label: str) -> None:
    """Log one line per product: type, short ID, mode and state key names."""
    LOG.info("--- %s: %d products ---", label, len(hive.data.products))
    rows = sorted(
        hive.data.products.items(), key=lambda item: (str(item[1].get("type")), item[0])
    )
    for product_id, product in rows:
        state = product.get("state") if isinstance(product.get("state"), dict) else {}
        LOG.info(
            "%-20s %-9s mode=%-9s keys=%s",
            product.get("type"),
            product_id[-SHORT_ID_LENGTH:],
            state.get("mode"),
            ", ".join(sorted(state)),
        )


async def run(args: argparse.Namespace, config: dict) -> None:
    """Start the session, then poll and log a summary until stopped."""
    hive = Hive(username=config["username"], password=config.get("password", ""))
    switch = {"on": False}
    async with hive:
        if args.drop:
            install_drop(hive, args.drop, switch)
        device_list = await hive.start_session(config)
        entities = ", ".join(f"{k}={len(v)}" for k, v in sorted(device_list.items()))
        LOG.info("Session started. Entities: %s", entities)
        log_summary(hive, "poll 1")

        if args.drop:
            switch["on"] = True
            LOG.info("Dropping state keys from later polls: %s", ", ".join(args.drop))
        poll = 1
        while args.polls == 0 or poll < args.polls:
            poll += 1
            await asyncio.sleep(args.interval)
            ok = await hive.force_update()
            log_summary(hive, f"poll {poll}{'' if ok else ' (FAILED)'}")


def _pid_file(name: str) -> Path:
    return LOG_DIR / f"{name}.pid"


def _running_pid(name: str) -> int | None:
    """Return the PID of the named runner if it is still our process."""
    try:
        pid = int(_pid_file(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    result = subprocess.run(
        ["ps", "-p", str(pid), "-o", "command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if Path(__file__).name in result.stdout:
        return pid
    _pid_file(name).unlink(missing_ok=True)
    return None


def _names() -> list[str]:
    return sorted(path.stem for path in LOG_DIR.glob("*.pid"))


def stop(name: str | None) -> None:
    """Stop the named runner, or every runner when *name* is None."""
    names = [name] if name else _names()
    stopped = False
    for runner in names:
        pid = _running_pid(runner)
        if pid is not None:
            os.kill(pid, signal.SIGTERM)
            _pid_file(runner).unlink(missing_ok=True)
            print(f"Stopped {runner} (pid {pid}).")
            stopped = True
    if not stopped:
        print("Nothing running.")


def status() -> None:
    """Print each running runner with its PID and log file."""
    running = [(name, _running_pid(name)) for name in _names()]
    running = [(name, pid) for name, pid in running if pid is not None]
    if not running:
        print("Nothing running.")
    for name, pid in running:
        print(f"{name}: running (pid {pid}) - {LOG_DIR / (name + '.log')}")


def launch(args: argparse.Namespace, name: str) -> None:
    """Log in if needed (foreground), then start the background worker."""
    pid = _running_pid(name)
    if pid is not None:
        sys.exit(f"{name} is already running (pid {pid}). Run `make stop` first.")
    if args.live:
        config = asyncio.run(live_config())
    else:
        config = {"username": FILE_USERNAME}

    LOG_DIR.mkdir(exist_ok=True)
    command = [sys.executable, __file__, "--worker", name]
    command += ["--polls", str(args.polls), "--interval", str(args.interval)]
    for key in args.drop:
        command += ["--drop", key]
    if args.debug:
        command.append("--debug")
    # Not a context manager: the worker must outlive this process.
    worker = subprocess.Popen(  # pylint: disable=consider-using-with
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
        text=True,
    )
    # The session config (tokens, password) goes over the pipe, not argv.
    if worker.stdin is not None:
        worker.stdin.write(json.dumps(config))
        worker.stdin.close()
    _pid_file(name).write_text(str(worker.pid), encoding="utf-8")
    print(f"Started {name} in the background (pid {worker.pid}).")
    print(f"Log: {LOG_DIR / (name + '.log')}")
    print("`make logs` to follow it, `make stop` to stop it.")


def work(args: argparse.Namespace) -> None:
    """Background worker: read the config from stdin and run until stopped."""
    config = json.loads(sys.stdin.read())
    LOG_DIR.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / f"{args.worker}.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUPS,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    logging.getLogger().addHandler(handler)
    LOG.setLevel(logging.INFO)
    logging.getLogger("apyhiveapi").setLevel(
        logging.DEBUG if args.debug else logging.WARNING
    )
    signal.signal(signal.SIGTERM, signal.default_int_handler)
    LOG.info("=== %s started (pid %d) ===", args.worker, os.getpid())
    try:
        asyncio.run(run(args, config))
        LOG.info("=== %s finished ===", args.worker)
    except KeyboardInterrupt:
        LOG.info("=== %s stopped ===", args.worker)
    except Exception:  # pylint: disable=broad-exception-caught
        LOG.exception("=== %s crashed ===", args.worker)
    finally:
        pid_file = _pid_file(args.worker)
        if pid_file.exists() and pid_file.read_text(encoding="utf-8") == str(
            os.getpid()
        ):
            pid_file.unlink()


def main() -> None:
    """Parse arguments and run."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--file", action="store_true", help="use the bundled fixture")
    mode.add_argument("--live", action="store_true", help="use a real Hive account")
    mode.add_argument(
        "--forget", action="store_true", help="delete the stored device credentials"
    )
    mode.add_argument("--stop", action="store_true", help="stop background runners")
    mode.add_argument("--status", action="store_true", help="list background runners")
    mode.add_argument("--worker", metavar="NAME", help=argparse.SUPPRESS)
    parser.add_argument("--name", help="runner to act on (default: derived, or all)")
    parser.add_argument(
        "--polls",
        type=int,
        default=0,
        help="polls to run; 0 (default) runs until stopped",
    )
    parser.add_argument(
        "--interval", type=float, default=120, help="seconds between polls"
    )
    parser.add_argument(
        "--drop",
        action="append",
        default=[],
        metavar="KEY",
        help="state key to strip from polls after the first (repeatable)",
    )
    parser.add_argument("--debug", action="store_true", help="library debug logging")
    args = parser.parse_args()

    if args.forget:
        forget_stored()
    elif args.stop:
        stop(args.name)
    elif args.status:
        status()
    elif args.worker:
        work(args)
    else:
        source = "live" if args.live else "file"
        launch(args, args.name or (f"simulate-{source}" if args.drop else source))


if __name__ == "__main__":
    main()
