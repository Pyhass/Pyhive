"""Device discovery mixin for HiveSession."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from ..helper.const import DEVICES, EXPECTED_DEVICE_DATA_LENGTH, HIVE_TYPES, PRODUCTS
from ..helper.hive_exceptions import HiveConnectionError, HiveUnknownConfiguration
from ..helper.hivedataclasses import Device

_DATA_DIR = Path(__file__).parent.parent / "data"

_LOGGER = logging.getLogger(__name__)


class DiscoveryMixin:
    """Device discovery, session start, and entity-list construction.

    Expects ``self.config``, ``self.data``, ``self.helper``,
    ``self.hub_id``, and ``self.device_list`` to be set up by the
    owning class's ``__init__``.
    """

    # Attributes provided by HiveSession.__init__
    config: Any
    data: Any
    auth: Any
    helper: Any
    hub_id: Any
    device_list: dict

    def open_file(self, file: str) -> dict:
        """Open a JSON fixture file from the package data directory.

        Args:
            file (str): Filename relative to the ``data/`` directory (e.g. ``"data.json"``).

        Returns:
            dict: Parsed JSON content of the file.
        """
        return json.loads((_DATA_DIR / file).read_text(encoding="utf-8"))

    def _configure_file_mode(self, username: str | None = None) -> None:
        """Set file mode when the magic testing username is detected.

        Args:
            username: If ``"use@file.com"``, switches the session to file-based mode.
        """
        if username == "use@file.com":
            self.config.file = True

    def add_list(self, entity_type: str, data: dict, **kwargs) -> Device | None:
        """Add entity to the device list.

        Args:
            entity_type (str): HA entity type (e.g. "climate", "sensor").
            data (dict): Raw product or device data from the Hive API.

        Returns:
            Device: Created device entity, or None on error.
        """
        try:
            hive_type = kwargs.get("hive_type", data.get("type", ""))
            if hive_type == "action":
                device_name = kwargs.get("ha_name", data.get("name", "Action"))
                device_obj = Device(
                    hive_id=data.get("id", ""),
                    hive_name=device_name,
                    hive_type="action",
                    ha_type=entity_type,
                    device_id=data.get("id", ""),
                    device_name=device_name,
                    device_data={},
                    parent_device=self.hub_id,
                    ha_name=device_name,
                )
            else:
                device_data = self.helper.get_device_data(data)
                device_name = (
                    device_data["state"]["name"]
                    if device_data["state"]["name"] != "Receiver"
                    else "Heating"
                )

                ha_name = kwargs.get("ha_name", "")
                if ha_name.startswith(" "):
                    ha_name = device_name + ha_name
                elif not ha_name:
                    ha_name = device_name

                device_obj = Device(
                    hive_id=data.get("id", ""),
                    hive_name=device_name,
                    hive_type=hive_type,
                    ha_type=entity_type,
                    device_id=device_data["id"],
                    device_name=device_name,
                    device_data=device_data.get("props", data.get("props", {})),
                    parent_device=self.hub_id,
                    is_group=data.get("isGroup", False),
                    ha_name=ha_name,
                    category=kwargs.get("category"),
                    temperature_unit=kwargs.get("temperature_unit"),
                )

                if data.get("type", "") == "hub":
                    self.device_list["parent"].append(device_obj)

            self.device_list[entity_type].append(device_obj)
            return device_obj
        except KeyError as error:
            _LOGGER.error(error)
            return None

    async def start_session(self, config: dict | None = None):
        """Setup the Hive platform.

        Args:
            config (dict, optional): Configuration for Home Assistant to use. Defaults to {}.

        Raises:
            HiveUnknownConfiguration: Unknown configuration identified.
            HiveReauthRequired: Tokens have expired and reauthentication is required.

        Returns:
            list: List of devices
        """
        if config is None:
            config = {}
        _LOGGER.debug("start_session - Starting Hive session.")
        _LOGGER.debug(
            "start_session - Config: %s", self.helper.sanitize_payload(config)
        )
        self._configure_file_mode(config.get("username", self.config.username))

        if config != {}:
            if "tokens" in config and not self.config.file:
                _LOGGER.debug("start_session - Updating tokens from config")
                await self.update_tokens(config["tokens"], False)  # type: ignore[attr-defined]

            if "username" in config and not self.config.file:
                self.auth.username = config["username"]

            if "password" in config and not self.config.file:
                self.auth.password = config["password"]

            if "device_data" in config and not self.config.file:
                device_data = config["device_data"]
                if len(device_data) < EXPECTED_DEVICE_DATA_LENGTH:
                    raise HiveUnknownConfiguration(
                        "device_data must contain device_group_key, "
                        "device_key and device_password"
                    )
                self.auth.device_group_key = device_data[0]
                self.auth.device_key = device_data[1]
                self.auth.device_password = device_data[2]
                if len(device_data) > EXPECTED_DEVICE_DATA_LENGTH:
                    token_created = device_data[3]
                    if token_created:
                        self.tokens.token_created = token_created  # type: ignore[attr-defined]

            if not self.config.file and "tokens" not in config:
                raise HiveUnknownConfiguration

        fetched = await self.get_devices("No_ID")  # type: ignore[attr-defined]

        if not self.data.devices or not self.data.products:
            if not fetched:
                # The request failed rather than returning an empty account,
                # so let the caller retry instead of treating it as bad config.
                raise HiveConnectionError("Could not fetch devices from Hive")
            _LOGGER.error("No devices or products returned from Hive API.")
            raise HiveUnknownConfiguration

        return await self.create_devices()

    async def create_devices(  # noqa: PLR0912, PLR0915
        self,
    ):  # pylint: disable=too-many-locals,too-many-statements
        """Create list of devices.

        Returns:
            list: List of devices
        """
        _LOGGER.info("create_devices - Starting device discovery process")

        self.device_list["parent"] = []
        self.device_list["binary_sensor"] = []
        self.device_list["climate"] = []
        self.device_list["light"] = []
        self.device_list["sensor"] = []
        self.device_list["switch"] = []
        self.device_list["water_heater"] = []

        hive_type = HIVE_TYPES["Thermo"] + HIVE_TYPES["Sensor"]

        # Find hub device first
        for a_device in self.data["devices"]:
            if self.data["devices"][a_device]["type"] == "hub":
                self.hub_id = a_device
                hub_name = (
                    self.data["devices"][a_device]
                    .get("state", {})
                    .get("name", a_device)
                )
                _LOGGER.debug(
                    "create_devices - Found hub device: %s (ID: %s)", hub_name, a_device
                )
                break
        else:
            _LOGGER.warning("create_devices - No hub device found in device list")

        # Process devices
        device_count = 0
        for a_device in self.data["devices"]:
            d = self.data.devices[a_device]
            device_name = d.get("state", {}).get("name", a_device)
            device_type = d.get("type", "Unknown")
            _LOGGER.debug(
                "create_devices - Processing device: %s (%s - %s)",
                device_name,
                a_device,
                device_type,
            )

            for entity_config in DEVICES.get(device_type, []):
                kwargs = {}
                if entity_config.ha_name:
                    kwargs["ha_name"] = entity_config.ha_name
                if entity_config.hive_type:
                    kwargs["hive_type"] = entity_config.hive_type
                if entity_config.category:
                    kwargs["category"] = entity_config.category
                try:
                    self.add_list(entity_config.entity_type, d, **kwargs)
                except (KeyError, TypeError, AttributeError) as e:
                    _LOGGER.error(
                        "Failed to create device entity for %s: %s",
                        device_name,
                        str(e),
                    )

            if device_type in hive_type:
                self.config.battery.add(d.get("id", a_device))
                _LOGGER.debug(
                    "create_devices - Added device %s to battery monitoring list",
                    device_name,
                )

            device_count += 1

        # Process actions
        _LOGGER.debug(
            "create_devices - Processing %d actions", len(self.data["actions"])
        )
        for action_id in self.data["actions"]:
            action = self.data["actions"][action_id]
            try:
                self.add_list(
                    "switch", action, ha_name=action["name"], hive_type="action"
                )
            except (KeyError, TypeError, AttributeError) as e:
                _LOGGER.error(
                    "Failed to create action entity for %s: %s",
                    action_id,
                    str(e),
                )

        # Process products
        hive_type = HIVE_TYPES["Heating"] + HIVE_TYPES["Switch"] + HIVE_TYPES["Light"]
        product_count = 0
        for a_product, p in self.data.products.items():
            if "error" in p:
                _LOGGER.warning(
                    "Skipping product %s due to error: %s", a_product, p["error"]
                )
                continue

            product_name = p.get("state", {}).get("name", a_product)
            product_type = p.get("type", "Unknown")
            _LOGGER.debug(
                "create_devices - Processing product: %s (%s - %s)",
                product_name,
                a_product,
                product_type,
            )

            if p.get("isGroup", False) and p["type"] not in HIVE_TYPES["Heating"]:
                _LOGGER.debug(
                    "create_devices - Skipping group product currently not supported %s (type: %s)",
                    product_name,
                    product_type,
                )
                continue

            for entity_config in PRODUCTS.get(product_type, []):
                kwargs = {}
                if entity_config.ha_name:
                    kwargs["ha_name"] = entity_config.ha_name
                if entity_config.hive_type:
                    kwargs["hive_type"] = entity_config.hive_type
                if entity_config.category:
                    kwargs["category"] = entity_config.category
                if entity_config.entity_type == "climate":
                    kwargs["temperature_unit"] = self.data["user"].get(
                        "temperatureUnit"
                    )
                elif entity_config.temperature_unit is not None:
                    kwargs["temperature_unit"] = entity_config.temperature_unit
                try:
                    self.add_list(entity_config.entity_type, p, **kwargs)
                except (NameError, AttributeError) as e:
                    _LOGGER.warning(
                        "create_devices - Device %s cannot be setup - %s",
                        product_name,
                        e,
                    )

            if product_type in hive_type:
                self.config.mode.add(p.get("id", a_product))
                _LOGGER.debug(
                    "create_devices - Added product %s to mode list", product_name
                )

            product_count += 1

        _LOGGER.info(
            "Device discovery completed: %d devices, %d products processed. "
            "Found: %d parent, %d binary_sensor, %d climate,"
            " %d light, %d sensor, %d switch, %d water_heater",
            device_count,
            product_count,
            len(self.device_list.get("parent", [])),
            len(self.device_list.get("binary_sensor", [])),
            len(self.device_list.get("climate", [])),
            len(self.device_list.get("light", [])),
            len(self.device_list.get("sensor", [])),
            len(self.device_list.get("switch", [])),
            len(self.device_list.get("water_heater", [])),
        )

        return self.device_list
