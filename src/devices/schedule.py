"""Shared weekly-schedule helpers for heating and hot water."""

from __future__ import annotations

import logging
from typing import Any

from ..helper.hivedataclasses import Device

_LOGGER = logging.getLogger(__name__)

DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
_MINUTES_PER_DAY = 1440

# Which key each product type expects inside a slot's ``value`` dict.
_VALUE_KEY = {
    "heating": "target",
    "trvcontrol": "target",
    "hotwater": "status",
}


class ScheduleMixin:
    """Read and write the full 7-day schedule for heating and hot water.

    The Hive API stores a product's schedule as a dict keyed by lowercase
    weekday name. Each day is a list of slots ``{"start": <minutes past
    midnight>, "value": {...}}``. Heating slots carry ``{"target": <°C>}``;
    hot water slots carry ``{"status": "ON" | "OFF"}``.

    Hive only accepts the whole week at once, so ``set_schedule`` always
    posts all seven days. Build the new schedule by editing the dict returned
    from ``get_schedule`` and pass it back.

    Expects ``self.session`` and the ``BaseDeviceHandler`` plumbing to be
    provided by the owning class.
    """

    session: Any

    async def get_schedule(self, device: Device) -> dict | None:
        """Return the product's full weekly schedule, or None if unavailable.

        The dict is a deep copy, so it can be edited and passed straight to
        ``set_schedule``.
        """
        schedule = self._get_product_state(  # type: ignore[attr-defined]
            device, "state", "schedule"
        )
        if not isinstance(schedule, dict):
            return None
        return {
            day: [
                {"start": slot["start"], "value": dict(slot["value"])} for slot in slots
            ]
            for day, slots in schedule.items()
        }

    async def set_schedule(self, device: Device, schedule: dict) -> bool:
        """Replace the product's weekly schedule.

        Args:
            device: Device whose schedule to set.
            schedule: Dict keyed by the seven lowercase weekday names, each a
                list of ``{"start": int, "value": dict}`` slots. Slots are
                normalised (extra keys dropped, sorted by start) before
                posting.

        Returns:
            True if Hive accepted the schedule and the refreshed product
            state matches what was sent; False otherwise.

        Raises:
            ValueError: If ``schedule`` is malformed. This is a caller bug,
                not an API failure, so it is raised rather than returned.
        """
        product_type = self._get_product_state(  # type: ignore[attr-defined]
            device, "type"
        )
        value_key = _VALUE_KEY.get(product_type)
        if value_key is None:
            _LOGGER.error(
                "set_schedule - %s (%s) does not support schedules",
                device.ha_name,
                product_type,
            )
            return False

        normalised = self._normalise_schedule(schedule, value_key)
        _LOGGER.info("set_schedule - Setting weekly schedule for %s", device.ha_name)
        changed = await self._execute_state_change(  # type: ignore[attr-defined]
            device, schedule=normalised
        )
        if not changed:
            return False

        # Hive answers 200 and echoes the payload even when it ignores it, so
        # confirm the refreshed product state actually carries the new schedule.
        stored = await self.get_schedule(device)
        if stored != normalised:
            _LOGGER.error(
                "set_schedule - Hive accepted the request for %s but the stored "
                "schedule does not match what was sent",
                device.ha_name,
            )
            return False
        return True

    @staticmethod
    def _normalise_schedule(schedule: dict, value_key: str) -> dict:
        """Validate a schedule and return a clean copy ready to post."""
        if not isinstance(schedule, dict):
            raise ValueError("schedule must be a dict keyed by weekday name")
        missing = [day for day in DAYS if day not in schedule]
        unknown = [day for day in schedule if day not in DAYS]
        if missing or unknown:
            raise ValueError(
                f"schedule must contain exactly the days {list(DAYS)}; "
                f"missing={missing} unknown={unknown}"
            )

        clean: dict = {}
        for day in DAYS:
            slots = schedule[day]
            if not isinstance(slots, list) or not slots:
                raise ValueError(f"{day}: expected a non-empty list of slots")
            day_slots = []
            for slot in slots:
                day_slots.append(ScheduleMixin._normalise_slot(day, slot, value_key))
            day_slots.sort(key=lambda s: s["start"])
            starts = [s["start"] for s in day_slots]
            if len(set(starts)) != len(starts):
                raise ValueError(f"{day}: duplicate slot start times {starts}")
            clean[day] = day_slots
        return clean

    @staticmethod
    def _normalise_slot(day: str, slot: Any, value_key: str) -> dict:
        """Validate one slot and return ``{"start": int, "value": {...}}``."""
        if not isinstance(slot, dict):
            raise ValueError(f"{day}: each slot must be a dict, got {slot!r}")
        start = slot.get("start")
        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or not 0 <= start < _MINUTES_PER_DAY
        ):
            raise ValueError(
                f"{day}: slot start must be an int in 0..{_MINUTES_PER_DAY - 1} "
                f"(minutes past midnight), got {start!r}"
            )
        value = slot.get("value")
        if not isinstance(value, dict) or value_key not in value:
            raise ValueError(
                f"{day}: slot at {start} needs a value dict containing "
                f"{value_key!r}, got {value!r}"
            )
        return {"start": start, "value": {value_key: value[value_key]}}
