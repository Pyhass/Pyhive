"""Round-trip a heating zone's weekly schedule through the Hive API.

Reads the zone's current schedule, nudges one slot's target by 0.5°C, posts it,
confirms Hive stored it, then restores the original. Nothing is changed
permanently. Requires a saved ``hive_device.json`` from ``example_login.py``.

Usage::

    python examples/example_set_schedule.py            # first climate zone
    python examples/example_set_schedule.py "Office"   # zone by name
"""

from __future__ import annotations

import asyncio
import copy
import getpass
import json
import os
import sys
from pathlib import Path

from apyhiveapi import Auth, Hive

DEVICE_FILE = Path(__file__).resolve().parent.parent / "hive_device.json"


async def login(username: str, password: str, device_data: list) -> dict:
    """Device login (no SMS) and return the start_session config."""
    auth = Auth(username, password, *device_data)
    result = await auth.login()
    if result.get("ChallengeName") == Auth.DEVICE_VERIFIER_CHALLENGE:
        result = await auth.device_login()
    auth_result = result["AuthenticationResult"]
    return {
        "username": username,
        "password": password,
        "device_data": device_data,
        "tokens": {
            "token": auth_result["IdToken"],
            "refreshToken": auth_result["RefreshToken"],
            "accessToken": auth_result["AccessToken"],
        },
    }


async def main() -> int:
    """Run the round trip and return a process exit code."""
    if not DEVICE_FILE.exists():
        print(f"No {DEVICE_FILE}; run examples/example_login.py first.")
        return 1
    saved = json.loads(DEVICE_FILE.read_text(encoding="utf-8"))
    password = os.environ.get("HIVE_PASSWORD") or getpass.getpass(
        "Hive password (hidden, not stored): "
    )
    wanted = sys.argv[1] if len(sys.argv) > 1 else None

    config = await login(saved["username"], password, saved["device_data"])
    async with Hive(username=saved["username"], password=password) as hive:
        device_list = await hive.start_session(config)
        zones = device_list["climate"]
        zone = (
            next((z for z in zones if z.ha_name == wanted), None)
            if wanted
            else zones[0]
        )
        if zone is None:
            print(
                f"No climate zone called {wanted!r}. Have: {[z.ha_name for z in zones]}"
            )
            return 1

        original = await hive.heating.get_schedule(zone)
        if original is None:
            print(f"{zone.ha_name} has no schedule in its product state.")
            return 1
        print(f"\n{zone.ha_name} ({zone.hive_type}) current monday:")
        print("  ", json.dumps(original["monday"]))

        changed = copy.deepcopy(original)
        slot = changed["monday"][0]
        slot["value"]["target"] = round(slot["value"]["target"] + 0.5, 1)
        print(f"\nSetting monday slot 0 target to {slot['value']['target']} ...")
        ok = await hive.heating.set_schedule(zone, changed)
        print("  set_schedule returned", ok)
        stored = await hive.heating.get_schedule(zone)
        print("  stored monday now:", json.dumps(stored["monday"]))
        print("  matches what we sent:", stored == changed)

        print("\nRestoring original schedule ...")
        ok_restore = await hive.heating.set_schedule(zone, original)
        print("  set_schedule returned", ok_restore)
        restored = await hive.heating.get_schedule(zone)
        print("  restored matches original:", restored == original)

    return 0 if ok and ok_restore and restored == original else 2


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
