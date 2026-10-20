"""Minimal standalone login example for pyhive-integration.

Run it once: it asks for your Hive email and password, completes the SMS
two-factor challenge, registers this machine as a trusted device and saves
the device credentials to ``hive_device.json`` in the working directory.
Run it again: it logs in with the saved device credentials, no SMS needed,
and lists the same devices.

    pip install pyhive-integration
    python examples/example_login.py

The password is never stored. The saved file holds a device password that
lets anyone with the file log in to your Hive account without an SMS code,
so keep it private (it is written with owner-only permissions). Delete the
file to force a fresh SMS login next time.

Only the Hive account owner can log in. Guest accounts are not supported.
"""

import asyncio
import getpass
import json
import os
import sys
from pathlib import Path

from apyhiveapi import SMS_REQUIRED, Auth, Hive
from apyhiveapi.helper.hive_exceptions import HiveInvalidDeviceAuthentication

DEVICE_FILE = Path("hive_device.json")


def load_device() -> dict:
    """Return the saved username and device credentials, or an empty dict."""
    if not DEVICE_FILE.exists():
        return {}
    try:
        return json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_device(username: str, device_data: list) -> None:
    """Save the username and device credentials with owner-only permissions."""
    DEVICE_FILE.write_text(
        json.dumps({"username": username, "device_data": device_data}, indent=2),
        encoding="utf-8",
    )
    os.chmod(DEVICE_FILE, 0o600)


def tokens_from(result: dict) -> dict:
    """Convert a Cognito AuthenticationResult into start_session tokens."""
    auth_result = result["AuthenticationResult"]
    return {
        "token": auth_result["IdToken"],
        "refreshToken": auth_result["RefreshToken"],
        "accessToken": auth_result["AccessToken"],
    }


async def device_login(username: str, password: str, device_data: list) -> dict:
    """Log in with saved device credentials. Returns {} if Hive rejects them."""
    auth = Auth(username, password, *device_data)
    try:
        # The password login comes first; Hive answers it with a device
        # challenge, which device_login() then completes without an SMS.
        result = await auth.login()
        if result.get("ChallengeName") == Auth.DEVICE_VERIFIER_CHALLENGE:
            result = await auth.device_login()
    except HiveInvalidDeviceAuthentication:
        return {}
    return result if "AuthenticationResult" in result else {}


async def sms_login(username: str, password: str) -> tuple[dict, list]:
    """Log in with password + SMS code and register this machine as a device."""
    auth = Auth(username, password)
    result = await auth.login()
    if result.get("ChallengeName") == SMS_REQUIRED:
        code = input("SMS code: ").strip()
        result = await auth.sms_2fa(code, result)
    if "AuthenticationResult" not in result:
        sys.exit(f"Login did not complete: {result.get('ChallengeName')}")

    device_data: list = []
    if auth.device_key:
        # Cognito ties the new tokens to this device. Without registering it
        # the refresh token is rejected and every login would need an SMS.
        await auth.device_registration()
        device_data = list((await auth.get_device_data())[:3])
    return result, device_data


async def build_config() -> dict:
    """Log in (reusing saved device credentials when possible)."""
    stored = load_device()
    username = stored.get("username") or input("Hive email: ").strip()
    password = getpass.getpass("Hive password (hidden, not stored): ")
    device_data = stored.get("device_data") or []

    result: dict = {}
    if device_data:
        print("Logging in with the saved device credentials (no SMS)...")
        result = await device_login(username, password, device_data)
        if not result:
            print("Hive rejected the saved device credentials - signing in again.")
            DEVICE_FILE.unlink(missing_ok=True)
            device_data = []

    if not result:
        print("Logging in with password + SMS...")
        result, device_data = await sms_login(username, password)
        if all(device_data):
            save_device(username, device_data)
            print(f"Device credentials saved to {DEVICE_FILE.resolve()}")
        else:
            print("Device credentials not available - the next run will need an SMS.")

    config = {"tokens": tokens_from(result), "username": username, "password": password}
    if all(device_data):
        config["device_data"] = device_data
    return config


async def main() -> None:
    """Log in, start a session and list the discovered devices."""
    config = await build_config()
    hive = Hive(username=config["username"], password=config["password"])
    async with hive:
        device_list = await hive.start_session(config)
        print("\nDevices:")
        for entity_type, devices in sorted(device_list.items()):
            for device in devices:
                print(f"  {entity_type:14} {device.hive_name}  ({device.hive_type})")


if __name__ == "__main__":
    asyncio.run(main())
