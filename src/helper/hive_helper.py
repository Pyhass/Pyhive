"""Helper class for pyhiveapi."""

import copy
import datetime
import logging
import operator
import time
from typing import Any

from .const import HIVE_TYPES

_LOGGER = logging.getLogger(__name__)


def epoch_time(date_time: Any, pattern: str, action: str) -> Any:
    """Convert between a datetime string and a Unix epoch integer.

    Args:
        date_time: Epoch integer or date/time string to convert.
        pattern: ``strptime``/``strftime`` format string used for the conversion.
        action: ``"to_epoch"`` converts a datetime string → int;
                ``"from_epoch"`` converts an int → formatted datetime string.

    Returns:
        Converted value, or ``None`` if *action* is unrecognised.
    """
    if action == "to_epoch":
        return int(time.mktime(time.strptime(str(date_time), pattern)))
    if action == "from_epoch":
        return datetime.datetime.fromtimestamp(int(date_time)).strftime(pattern)
    return None


class HiveHelper:
    """Hive helper class."""

    def __init__(self, session: Any = None):
        """Hive Helper.

        Args:
            session (object, optional): Interact with hive account. Defaults to None.
        """
        self.session = session

    async def get_device_name(self, n_id: str):
        """Resolve a id into a name.

        Args:
            n_id (str): ID of a device.

        Returns:
            str: Name of device.
        """
        product_name: str | None = None
        device_name: str | None = None

        try:
            product_name = self.session.data.products[n_id]["state"]["name"]
        except KeyError:
            pass

        try:
            device_name = self.session.data.devices[n_id]["state"]["name"]
        except KeyError:
            pass

        if not product_name and not device_name:
            _LOGGER.warning(
                "get_device_name - No product or device name found for ID: %s", n_id
            )

        if product_name:
            final_name = product_name
        elif device_name:
            final_name = device_name
        elif n_id == "No_ID":
            final_name = "Hive"
        else:
            final_name = n_id

        return final_name

    def device_recovered(self, n_id: str):
        """Register that a device has recovered from being offline.

        Args:
            n_id (str): ID of the device.
        """
        # name = HiveHelper.get_device_name(n_id)
        if n_id in self.session.config.error_list:
            self.session.config.error_list.pop(n_id)

    async def error_check(self, n_id, _n_type, error_type, **_kwargs):
        """Error has occurred."""
        message = None
        name = await self.get_device_name(n_id)
        device_name = name if isinstance(name, str) else n_id

        if error_type is False:
            message = "Device offline could not update entity - " + str(device_name)
            if n_id not in self.session.config.error_list:
                _LOGGER.warning(message)
                self.session.config.error_list.update({n_id: datetime.datetime.now()})
        elif error_type == "Failed":
            message = "ERROR - No data found for device - " + str(device_name)
            if n_id not in self.session.config.error_list:
                _LOGGER.error(message)
                self.session.config.error_list.update({n_id: datetime.datetime.now()})

    def get_device_from_id(self, n_id: str):
        """Get product/device data from ID.

        Args:
            n_id (str): ID of the device.

        Returns:
            dict: Device data.
        """
        if hasattr(self.session, "entity_cache"):
            for cached_id, cached in self.session.entity_cache.items():
                hive_id = (
                    cached.get("hive_id")
                    if isinstance(cached, dict)
                    else getattr(cached, "hive_id", None)
                )
                device_id = (
                    cached.get("device_id")
                    if isinstance(cached, dict)
                    else getattr(cached, "device_id", None)
                )
                if n_id in (hive_id, device_id):
                    ha_name = (
                        cached.get("haName", cached_id)
                        if isinstance(cached, dict)
                        else getattr(cached, "ha_name", cached_id)
                    )
                    _LOGGER.debug(
                        "get_device_from_id - Found cached device for ID %s: %s",
                        n_id,
                        ha_name,
                    )
                    return cached
        return False

    def get_device_data(self, product: dict):
        """Get device from product data.

        Args:
            product (dict): Product data.

        Returns:
            [type]: Device data.
        """
        product_id = product.get("id", "Unknown")
        device = product
        product_type = product["type"]
        if product_type in ("heating", "hotwater"):
            product_zone = product.get("props", {}).get("zone")
            for a_device in self.session.data.devices:
                if self.session.data.devices[a_device]["type"] in HIVE_TYPES["Thermo"]:
                    device_zone = (
                        self.session.data.devices[a_device].get("props", {}).get("zone")
                    )
                    if product_zone and device_zone and product_zone == device_zone:
                        device = self.session.data.devices[a_device]
        elif product_type == "trvcontrol":
            trv_present = len(product["props"]["trvs"]) > 0
            if trv_present:
                device = self.session.data.devices[product["props"]["trvs"][0]]
            else:
                _LOGGER.error(
                    "get_device_data - No TRVs found for product %s", product_id
                )
                raise KeyError
        elif (
            product_type == "warmwhitelight" and product["props"]["model"] == "SIREN001"
        ):
            device = self.session.data.devices[product["parent"]]
        elif product_type == "sense":
            device = self.session.data.devices[product["parent"]]
        else:
            device = self.session.data.devices[product["id"]]

        return device

    def convert_minutes_to_time(self, minutes_to_convert: int):
        """Convert minutes string to datetime.

        Args:
            minutes_to_convert (str): minutes in string value.

        Returns:
            timedelta: time object of the minutes.
        """
        hours_converted, minutes_converted = divmod(minutes_to_convert, 60)
        converted_time = datetime.datetime.strptime(
            str(hours_converted) + ":" + str(minutes_converted), "%H:%M"
        )
        converted_time_string = converted_time.strftime("%H:%M")
        return converted_time_string

    def get_schedule_nnl(self, hive_api_schedule: dict):  # pylint: disable=too-many-locals
        """Get the schedule now, next and later of a given nodes schedule.

        Args:
            hive_api_schedule (list): Schedule to parse.

        Returns:
            dict: Now, Next and later values.
        """
        _LOGGER.debug(
            "get_schedule_nnl - Parsing schedule NNL for %d days",
            len(hive_api_schedule),
        )
        schedule_now_and_next = {}
        date_time_now = datetime.datetime.now()
        date_time_now_day_int = date_time_now.today().weekday()

        days_t = (
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        )

        days_rolling_list = list(days_t[date_time_now_day_int:] + days_t)[:7]
        _LOGGER.debug("get_schedule_nnl - Days rolling list: %s", days_rolling_list)

        full_schedule_list = []

        for day_index, day_name in enumerate(days_rolling_list):
            current_day_schedule = hive_api_schedule[day_name]
            current_day_schedule_sorted = sorted(
                current_day_schedule,
                key=operator.itemgetter("start"),
                reverse=False,
            )
            _LOGGER.debug(
                "get_schedule_nnl - Processing day %s with %d schedule slots",
                day_name,
                len(current_day_schedule_sorted),
            )

            for current_slot_custom in current_day_schedule_sorted:
                slot_date = datetime.datetime.now() + datetime.timedelta(days=day_index)
                slot_time = self.convert_minutes_to_time(current_slot_custom["start"])
                slot_time_date_s = slot_date.strftime("%d-%m-%Y") + " " + slot_time
                slot_time_date_dt = datetime.datetime.strptime(
                    slot_time_date_s, "%d-%m-%Y %H:%M"
                )
                if slot_time_date_dt <= date_time_now:
                    slot_time_date_dt = slot_time_date_dt + datetime.timedelta(days=7)

                slot_copy = dict(current_slot_custom)
                slot_copy["Start_DateTime"] = slot_time_date_dt
                full_schedule_list.append(slot_copy)

        fsl_sorted = sorted(
            full_schedule_list,
            key=operator.itemgetter("Start_DateTime"),
            reverse=False,
        )

        if len(fsl_sorted) >= 3:  # noqa: PLR2004
            schedule_now = fsl_sorted[-1]
            schedule_next = fsl_sorted[0]
            schedule_later = fsl_sorted[1]

            schedule_now["Start_DateTime"] = schedule_now[
                "Start_DateTime"
            ] - datetime.timedelta(days=7)

            schedule_now["End_DateTime"] = schedule_next["Start_DateTime"]
            schedule_next["End_DateTime"] = schedule_later["Start_DateTime"]
            schedule_later["End_DateTime"] = fsl_sorted[2]["Start_DateTime"]

            schedule_now_and_next["now"] = schedule_now
            schedule_now_and_next["next"] = schedule_next
            schedule_now_and_next["later"] = schedule_later

            _LOGGER.debug(
                "get_schedule_nnl - Schedule NNL parsed successfully"
                " - now: %s, next: %s, later: %s",
                schedule_now.get("Start_DateTime"),
                schedule_next.get("Start_DateTime"),
                schedule_later.get("Start_DateTime"),
            )
        else:
            _LOGGER.warning(
                "get_schedule_nnl - Insufficient schedule data (%d slots) for NNL calculation",
                len(fsl_sorted),
            )

        return schedule_now_and_next

    def sanitize_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return a copy of payload with sensitive values masked for logs."""

        def _mask(value: Any) -> Any:
            if isinstance(value, str):
                if len(value) <= 8:  # noqa: PLR2004
                    return "***"
                return f"{value[:4]}...{value[-4:]}"
            if isinstance(value, dict):
                return {k: _mask(v) for k, v in value.items()}
            if isinstance(value, list):
                return [_mask(item) for item in value]
            return value

        def _walk(node: Any) -> Any:
            if isinstance(node, dict):
                result: dict[str, Any] = {}
                for key, value in node.items():
                    key_lower = key.lower()
                    if any(
                        part in key_lower
                        for part in (
                            "password",
                            "token",
                            "tokens",
                            "secret",
                            "code",
                            "session",
                            "accesstoken",
                            "device_data",
                            "authenticationresult",
                            "responsemetadata",
                            "newdevicemetadata",
                        )
                    ):
                        result[key] = _mask(value)
                    else:
                        result[key] = _walk(value)
                return result
            if isinstance(node, list):
                return [_walk(item) for item in node]
            return node

        return _walk(copy.deepcopy(payload))
