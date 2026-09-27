# pyhive-integration

![CI](https://github.com/Pyhass/Pyhive/actions/workflows/ci.yml/badge.svg) ![PyPI](https://img.shields.io/pypi/v/pyhive-integration) ![Python](https://img.shields.io/pypi/pyversions/pyhive-integration) ![License](https://img.shields.io/github/license/Pyhass/Pyhive)

A Python library for interfacing with the [Hive](https://www.hivehome.com/) smart home platform. Provides both async (`apyhiveapi`) and sync (`pyhiveapi`) APIs, and is designed primarily for use with [Home Assistant](https://www.home-assistant.io/) — though it works standalone too.

> **Package rename notice:** This package replaces the legacy `pyhiveapi` package. The module names, API, and functionality are identical — only the PyPI distribution name changed.

---

## Features

- Async-first design with a generated sync wrapper (no asyncio boilerplate needed in sync contexts)
- AWS Cognito SRP authentication with SMS two-factor authentication support
- Automatic token refresh at 90% of token lifetime with silent retry on expiry
- Polling-based device state with a smart cache to avoid stale reads during in-progress polls
- Full device discovery — returns a ready-to-use device list for Home Assistant entity creation
- File-based offline mode for development and testing without live credentials

## Supported Devices

| Device Type | Capabilities |
| --- | --- |
| **Heating** (thermostat, TRV) | Current / target temperature, mode (schedule / manual / off), boost on/off, heat-on-demand, min/max range, schedule now/next/later |
| **Hot Water** | Mode (schedule / on / off), boost on/off, state |
| **Lights** | On/off, brightness, colour temperature, full RGB colour, colour mode |
| **Smart Plugs** | On/off, power usage |
| **Sensors** | Motion, contact (open/close), battery level, online status |
| **Hub / Sense** | Smoke, CO, dog bark, glass break detection |

---

## Installation

```bash
pip install pyhive-integration
```

Requires Python 3.10+.

---

## Quick Start

### Async

```python
import asyncio
from apyhiveapi import Auth, Hive

async def main():
    auth = Auth(username="user@example.com", password="yourpassword")
    tokens = await auth.login()

    # If SMS 2FA is required:
    # tokens = await auth.sms_2fa("123456", tokens)

    hive = Hive(username="user@example.com", password="yourpassword")
    await hive.startSession({"tokens": tokens})

    for device in hive.session.data.devices.values():
        print(device)

asyncio.run(main())
```

### Sync

```python
from pyhiveapi import Auth, Hive

auth = Auth(username="user@example.com", password="yourpassword")
tokens = auth.login()

hive = Hive(username="user@example.com", password="yourpassword")
hive.startSession({"tokens": tokens})

for device in hive.session.data.devices.values():
    print(device)
```

---

## Authentication

Authentication uses the AWS Cognito SRP flow. If your account has SMS two-factor authentication enabled, `login()` will raise `HiveSmsRequired` — call `sms_2fa(code, tokens)` with the code sent to your phone.

```python
from apyhiveapi import Auth
from apyhiveapi.helper.hive_exceptions import HiveSmsRequired

auth = Auth(username="user@example.com", password="yourpassword")
try:
    tokens = await auth.login()
except HiveSmsRequired:
    code = input("SMS code: ")
    tokens = await auth.sms_2fa(code, tokens)
```

> **Note:** Only the Hive account owner is supported. Guest accounts cannot be used.

---

## Controlling Devices

After `startSession`, device modules are available directly on the `Hive` instance:

```python
# Heating
await hive.heating.set_target_temperature(device, 21.0)
await hive.heating.set_mode(device, "SCHEDULE")
await hive.heating.set_boost_on(device, mins=30, temp=22.0)
await hive.heating.set_boost_off(device)

# Hot water
await hive.hotwater.set_mode(device, "ON")
await hive.hotwater.set_boost_on(device, mins=60)

# Lights
await hive.light.set_status_on(device)
await hive.light.set_brightness(device, 80)
await hive.light.set_color_temp(device, 4000)
await hive.light.set_color(device, [255, 100, 0])

# Smart plug
await hive.switch.turn_on(device)
await hive.switch.turn_off(device)

# Force a data refresh
await hive.force_update()
```

---

## Offline / File-Based Testing

Set `username="use@file.com"` to load device state from bundled JSON fixtures in `src/data/` instead of making live API calls. Useful for development without real Hive credentials.

```python
hive = Hive(username="use@file.com", password="")
await hive.startSession({})
```

---

## Architecture

The library exposes two packages built from the same source:

- **`apyhiveapi`** — async package (source in `src/`)
- **`pyhiveapi`** — sync package (auto-generated from `src/` via `unasync` during build)

Never edit the generated sync files — edit the async source in `src/` only.

---

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run linters
pre-commit run --all-files

# Run tests
pytest tests/

# Regenerate sync package
python setup.py build_py
```

---

## Links

- [PyPI](https://pypi.org/project/pyhive-integration/)
- [Source](https://github.com/Pyhass/Pyhive)
- [Issue Tracker](https://github.com/Pyhass/Pyhive/issues)

---

## License

MIT License — see [LICENSE](https://github.com/Pyhass/Pyhive/blob/master/LICENSE) for details.

<!-- Test PR: verifying Claude review bot identity on same-repo PRs. Do not merge. -->
