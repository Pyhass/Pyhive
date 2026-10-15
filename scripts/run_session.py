"""Run a Hive session in the background for local testing.

Starts a session against the bundled fixture (``--file``) or a real Hive
account (``--live``) as a background process that polls until it is stopped
(``--stop``), logging the shape of each product's state to ``logs/``.

A running session takes admin commands (``--call``) over a local socket in
``logs/``. It is read-only unless started with ``--allow-writes``: without
that flag every command that would change a device is refused.

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
import inspect
import json
import logging
import logging.handlers
import os
import shutil
import signal
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
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

CALL_TIMEOUT = 60
MODE_TYPES = ("climate", "water_heater")
SWITCHABLE_TYPES = ("light", "switch")

LOG = logging.getLogger("run_session")


@dataclass
class Settings:
    """What a running session can have changed by an admin command."""

    interval: float
    allow_writes: bool = False
    drop_keys: list[str] = field(default_factory=list)
    drop_on: bool = False


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

    result: dict = {}
    if device_data:
        print("Logging in with the stored device credentials (no SMS)...")
        auth = Auth(username, password, *device_data)
        try:
            # The password login comes first; Hive answers it with a device
            # challenge, which device_login() then completes.
            result = await auth.login()
            if result.get("ChallengeName") == Auth.DEVICE_VERIFIER_CHALLENGE:
                result = await auth.device_login()
        except HiveInvalidDeviceAuthentication:
            result = {}
        if "AuthenticationResult" not in result:
            print("Hive rejected the stored device credentials - signing in again.")
            forget_stored()
            device_data = None

    if not device_data:
        print("Logging in...")
        auth = Auth(username, password)
        result = await auth.login()
        if result.get("ChallengeName") == SMS_REQUIRED:
            code = input("SMS code: ").strip()
            result = await auth.sms_2fa(code, result)
        if "AuthenticationResult" not in result:
            sys.exit(f"Login did not complete: {result.get('ChallengeName')}")
        if auth.device_key:
            # Cognito ties the new tokens to this device: without registering
            # it the refresh token is rejected and the next login needs an SMS.
            await auth.device_registration()
        device_data = list((await auth.get_device_data())[:3])
        if all(device_data) and save_stored(username, device_data):
            print("Device credentials saved in the macOS Keychain.")
        else:
            print("Device credentials not saved - the next run will need an SMS.")

    config = {"tokens": _tokens(result), "username": username, "password": password}
    if all(device_data):
        config["device_data"] = device_data
    return config


def install_drop(hive: Hive, settings: Settings) -> None:
    """Strip ``settings.drop_keys`` from product state while ``drop_on`` is set.

    Simulates the incomplete responses Hive occasionally returns.
    """

    def _strip(response):
        if settings.drop_on and isinstance(response, dict):
            for product in (response.get("parsed") or {}).get("products", []):
                state = product.get("state")
                if isinstance(state, dict):
                    for key in settings.drop_keys:
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


class Admin:
    """The commands a running session accepts over its control socket.

    A fixed list rather than "call anything": the session object also holds
    the account's tokens and password, which no command hands out.
    """

    def __init__(self, hive: Hive, settings: Settings) -> None:
        """Bind the commands to a started session."""
        self.hive = hive
        self.settings = settings
        # name: (handler, changes a device, arguments, description)
        self.commands: dict[str, tuple[Callable[..., Awaitable], bool, str, str]] = {
            "help": (self.help, False, "", "list the commands"),
            "devices": (self.devices, False, "", "list the controllable devices"),
            "poll": (self.poll, False, "", "poll Hive now"),
            "mode": (self.mode, False, "DEVICE", "mode the library reports"),
            "state": (self.state, False, "DEVICE", "state as last received"),
            "drop": (self.drop, False, "KEY... | off", "strip state keys from polls"),
            "debug": (self.debug, False, "on | off", "library debug logging"),
            "interval": (self.interval, False, "SECONDS", "seconds between polls"),
            "set-mode": (self.set_mode, True, "DEVICE MODE", "set heating/hot water"),
            "set-temp": (self.set_temp, True, "DEVICE TEMP", "set target temperature"),
            "boost": (self.boost, True, "DEVICE MINS [TEMP]", "start a boost"),
            "boost-off": (self.boost_off, True, "DEVICE", "cancel a boost"),
            "turn-on": (self.turn_on, True, "DEVICE", "turn a light or plug on"),
            "turn-off": (self.turn_off, True, "DEVICE", "turn a light or plug off"),
        }

    def _find(self, ref: str, types: tuple[str, ...]):
        """Return the one device of *types* matching a name or ID suffix."""
        matches = [
            device
            for ha_type in types
            for device in self.hive.device_list.get(ha_type, [])
            if device.ha_name.lower() == ref.lower() or device.hive_id.endswith(ref)
        ]
        if len(matches) != 1:
            found = "no" if not matches else f"{len(matches)}"
            raise ValueError(
                f"{found} {'/'.join(types)} device matches {ref!r} - see `devices`"
            )
        return matches[0]

    def _module(self, device):
        return {
            "climate": self.hive.heating,
            "water_heater": self.hive.hotwater,
            "light": self.hive.light,
            "switch": self.hive.switch,
        }[device.ha_type]

    async def run(self, name: str, args: list[str]):
        """Run one command and return its JSON-serialisable result."""
        if name not in self.commands:
            raise ValueError(f"unknown command {name!r} - try `help`")
        handler, writes, _, _ = self.commands[name]
        if writes and not self.settings.allow_writes:
            raise PermissionError(
                f"{name} changes a device and this session is read-only. "
                "Restart it with WRITE=1 to allow that."
            )
        try:
            inspect.signature(handler).bind(*args)
        except TypeError as error:
            raise ValueError(self._usage(name)) from error
        return await handler(*args)

    def _usage(self, name: str) -> str:
        return f"usage: {name} {self.commands[name][2]}"

    async def help(self):
        """List the commands, marking the ones this session refuses."""
        return {
            "writes_allowed": self.settings.allow_writes,
            "commands": [
                f"{name} {usage}".strip().ljust(28)
                + description
                + (" [needs WRITE=1]" if writes else "")
                for name, (_, writes, usage, description) in self.commands.items()
            ],
        }

    async def devices(self):
        """List the devices the other commands can address."""
        return [
            f"{device.ha_type:<13}{device.hive_id[-SHORT_ID_LENGTH:]}  {device.ha_name}"
            for ha_type in MODE_TYPES + SWITCHABLE_TYPES
            for device in self.hive.device_list.get(ha_type, [])
        ]

    async def poll(self):
        """Poll now; False means it failed or one was already running."""
        ok = await self.hive.force_update()
        log_summary(self.hive, f"admin poll{'' if ok else ' (FAILED)'}")
        return ok

    async def mode(self, ref: str):
        """Return what get_mode reports for a heating or hot water device."""
        device = self._find(ref, MODE_TYPES)
        return await self._module(device).get_mode(device)

    async def state(self, ref: str):
        """Return a device's state block, without its schedule."""
        device = self._find(ref, MODE_TYPES + SWITCHABLE_TYPES)
        state = self.hive.data.products.get(device.hive_id, {}).get("state") or {}
        return {key: value for key, value in state.items() if key != "schedule"}

    async def drop(self, *keys: str):
        """Strip *keys* from every later poll, or stop with ``off``."""
        if not keys:
            raise ValueError(self._usage("drop"))
        self.settings.drop_on = keys != ("off",)
        if self.settings.drop_on:
            self.settings.drop_keys[:] = keys
        return {"dropping": self.settings.drop_keys if self.settings.drop_on else []}

    async def debug(self, switch: str):
        """Turn the library's debug logging on or off."""
        if switch not in ("on", "off"):
            raise ValueError(self._usage("debug"))
        level = logging.DEBUG if switch == "on" else logging.WARNING
        logging.getLogger("apyhiveapi").setLevel(level)
        return {"debug": switch}

    async def interval(self, seconds: str):
        """Change the polling interval, from the next wait onwards."""
        value = float(seconds)
        if value < 1:
            raise ValueError("interval must be at least 1 second")
        self.settings.interval = value
        return {"interval": value, "applies": "after the current wait"}

    async def set_mode(self, ref: str, new_mode: str):
        """Set a heating or hot water mode."""
        device = self._find(ref, MODE_TYPES)
        return await self._module(device).set_mode(device, new_mode.upper())

    async def set_temp(self, ref: str, temp: str):
        """Set a heating target temperature."""
        device = self._find(ref, ("climate",))
        return await self.hive.heating.set_target_temperature(device, float(temp))

    async def boost(self, ref: str, mins: str, temp: str | None = None):
        """Start a heating (needs TEMP) or hot water boost."""
        device = self._find(ref, MODE_TYPES)
        if device.ha_type == "water_heater":
            return await self.hive.hotwater.set_boost_on(device, int(mins))
        if temp is None:
            raise ValueError(
                "a heating boost needs a temperature: boost DEVICE MINS TEMP"
            )
        return await self.hive.heating.set_boost_on(device, mins, float(temp))

    async def boost_off(self, ref: str):
        """Cancel a boost."""
        device = self._find(ref, MODE_TYPES)
        return await self._module(device).set_boost_off(device)

    async def turn_on(self, ref: str):
        """Turn a light or plug on."""
        device = self._find(ref, SWITCHABLE_TYPES)
        if device.ha_type == "light":
            return await self.hive.light.turn_on(device, None, None, None)
        return await self.hive.switch.turn_on(device)

    async def turn_off(self, ref: str):
        """Turn a light or plug off."""
        device = self._find(ref, SWITCHABLE_TYPES)
        return await self._module(device).turn_off(device)

    async def serve(self, reader, writer) -> None:
        """Answer one request: a JSON line in, a JSON line out."""
        try:
            request = json.loads(await reader.readline())
            name, args = request["command"], request.get("args", [])
            LOG.info("admin: %s %s", name, " ".join(args))
            try:
                reply = {"ok": True, "result": await self.run(name, args)}
            except (ValueError, PermissionError) as error:
                reply = {"ok": False, "error": str(error)}
            except Exception as error:  # pylint: disable=broad-exception-caught
                LOG.exception("admin: %s failed", name)
                reply = {"ok": False, "error": f"{type(error).__name__}: {error}"}
            LOG.info("admin: %s -> %s", name, json.dumps(reply, default=str))
            writer.write(json.dumps(reply, default=str).encode() + b"\n")
            await writer.drain()
        finally:
            writer.close()


async def run(args: argparse.Namespace, config: dict) -> None:
    """Start the session, then poll and log a summary until stopped."""
    hive = Hive(username=config["username"], password=config.get("password", ""))
    settings = Settings(
        interval=args.interval,
        allow_writes=args.allow_writes,
        drop_keys=list(args.drop),
    )
    async with hive:
        install_drop(hive, settings)
        device_list = await hive.start_session(config)
        entities = ", ".join(f"{k}={len(v)}" for k, v in sorted(device_list.items()))
        LOG.info("Session started. Entities: %s", entities)
        log_summary(hive, "poll 1")

        if args.drop:
            settings.drop_on = True
            LOG.info("Dropping state keys from later polls: %s", ", ".join(args.drop))
        if settings.allow_writes:
            LOG.warning("Admin commands that change devices are ENABLED.")
        socket_path = _socket_file(args.worker)
        socket_path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(
            Admin(hive, settings).serve, path=str(socket_path)
        )
        socket_path.chmod(0o600)
        async with server:
            poll = 1
            while args.polls == 0 or poll < args.polls:
                poll += 1
                await asyncio.sleep(settings.interval)
                ok = await hive.force_update()
                log_summary(hive, f"poll {poll}{'' if ok else ' (FAILED)'}")


def _pid_file(name: str) -> Path:
    return LOG_DIR / f"{name}.pid"


def _socket_file(name: str) -> Path:
    return LOG_DIR / f"{name}.sock"


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


async def _send(name: str, command: list[str]) -> dict:
    reader, writer = await asyncio.open_unix_connection(str(_socket_file(name)))
    request = {"command": command[0], "args": command[1:]}
    writer.write(json.dumps(request).encode() + b"\n")
    await writer.drain()
    try:
        return json.loads(await asyncio.wait_for(reader.readline(), CALL_TIMEOUT))
    finally:
        writer.close()


def call(name: str | None, command: list[str]) -> None:
    """Run an admin command inside a running session and print the reply."""
    running = [runner for runner in _names() if _running_pid(runner) is not None]
    if name is None and len(running) == 1:
        name = running[0]
    if name not in running:
        sys.exit(
            f"Pick a running session with NAME=<runner>. Running: "
            f"{', '.join(running) or 'none'}."
        )
    try:
        reply = asyncio.run(_send(name, command))
    except (OSError, ValueError, asyncio.TimeoutError) as error:
        sys.exit(f"Could not reach {name}: {error or type(error).__name__}")
    if not reply.get("ok"):
        sys.exit(f"{name}: {reply.get('error')}")
    result = reply.get("result")
    if isinstance(result, dict) and isinstance(result.get("commands"), list):
        print(f"writes allowed: {result['writes_allowed']}")
        result = result["commands"]
    if isinstance(result, list):
        print("\n".join(str(item) for item in result))
    else:
        print(json.dumps(result, indent=2, default=str))


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
    if args.allow_writes:
        command.append("--allow-writes")
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
        _socket_file(args.worker).unlink(missing_ok=True)
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
    mode.add_argument(
        "--call",
        nargs="+",
        metavar="WORD",
        help="run an admin command inside a running session (try: --call help)",
    )
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
    parser.add_argument(
        "--allow-writes",
        action="store_true",
        help="let admin commands change devices (default: read-only)",
    )
    args = parser.parse_args()

    if args.forget:
        forget_stored()
    elif args.stop:
        stop(args.name)
    elif args.status:
        status()
    elif args.call:
        call(args.name, args.call)
    elif args.worker:
        work(args)
    else:
        source = "live" if args.live else "file"
        launch(args, args.name or (f"simulate-{source}" if args.drop else source))


if __name__ == "__main__":
    main()
