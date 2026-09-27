"""Device and session data classes."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

_SCAN_INTERVAL = timedelta(seconds=120)

_SENTINEL = object()

_DEVICE_KEY_MAP = {
    "hiveID": "hive_id",
    "hiveName": "hive_name",
    "hiveType": "hive_type",
    "haName": "ha_name",
    "haType": "ha_type",
    "deviceData": "device_data",
    "parentDevice": "parent_device",
    "temperatureunit": "temperature_unit",
}


@dataclass
class Device:
    """Class for keeping track of a device."""

    hive_id: str
    hive_name: str
    hive_type: str
    ha_type: str
    device_id: str
    device_name: str
    device_data: dict
    parent_device: str | None = None
    is_group: bool = False
    ha_name: str = ""
    category: str | None = None
    temperature_unit: str | None = None
    status: dict | None = None
    data: dict | None = None
    attributes: dict | None = None
    min_temp: float | None = None
    max_temp: float | None = None

    def _resolve(self, key: str) -> str:
        """Translate a legacy camelCase key to the current snake_case attribute name."""
        return _DEVICE_KEY_MAP.get(key, key)

    def __getitem__(self, key: str):
        """Support dict-style read access, resolving legacy camelCase keys."""
        try:
            return getattr(self, self._resolve(key))
        except AttributeError:
            raise KeyError(key) from None

    def __setitem__(self, key: str, value) -> None:
        """Support dict-style write access, resolving legacy camelCase keys."""
        setattr(self, self._resolve(key), value)

    def __contains__(self, key: str) -> bool:
        """Return True if the key resolves to a non-None attribute."""
        val = getattr(self, self._resolve(key), _SENTINEL)
        return val is not _SENTINEL and val is not None

    def get(self, key: str, default=None):
        """Return the value for key, or default if missing or None."""
        try:
            val = self[key]
            return val if val is not None else default
        except KeyError:
            return default


@dataclass
class EntityConfig:
    """Configuration for creating a device entity."""

    entity_type: Literal[
        "sensor",
        "binary_sensor",
        "climate",
        "light",
        "switch",
        "water_heater",
    ]
    ha_name: str = ""
    hive_type: str = ""
    category: str | None = None
    temperature_unit: str | None = None


@dataclass
class SessionTokens:
    """Typed container for session authentication tokens."""

    token_data: dict = field(default_factory=dict)
    token_created: datetime = field(default_factory=lambda: datetime.min)
    token_expiry: timedelta = field(default_factory=lambda: timedelta(seconds=3600))


@dataclass
class SessionConfig:
    """Typed container for session configuration state."""

    battery: set = field(default_factory=set)
    error_list: dict = field(default_factory=dict)
    file: bool = False
    home_id: str | None = None
    last_update: datetime = field(default_factory=datetime.now)
    mode: set = field(default_factory=set)
    scan_interval: timedelta = field(default_factory=lambda: _SCAN_INTERVAL)
    user_id: str | None = None
    username: str | None = None
