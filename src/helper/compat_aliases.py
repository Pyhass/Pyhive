"""Backwards-compatible camelCase method aliases for Home Assistant integration.

The HA integration historically called camelCase methods (``turnOn``, ``setMode``, etc.).
These mixins preserve that API so the integration does not need to be updated.
"""
# pylint: disable=no-member

from __future__ import annotations

from datetime import timedelta
from typing import Any

from .hivedataclasses import Device


class HeatingCompatMixin:
    """CamelCase aliases for Climate (heating) public methods."""

    async def setMode(self, device: Device, new_mode: str):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_mode."""
        return await self.set_mode(device, new_mode)  # type: ignore[attr-defined]

    async def setTargetTemperature(self, device: Device, new_temp: str):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_target_temperature."""
        return await self.set_target_temperature(device, new_temp)  # type: ignore[attr-defined]

    async def setBoostOn(self, device: Device, mins: str, temp: float):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_boost_on."""
        return await self.set_boost_on(device, mins, temp)  # type: ignore[attr-defined]

    async def setBoostOff(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_boost_off."""
        return await self.set_boost_off(device)  # type: ignore[attr-defined]

    async def setHeatOnDemand(self, device: Device, state: str):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_heat_on_demand."""
        return await self.set_heat_on_demand(device, state)  # type: ignore[attr-defined]

    async def getClimate(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_climate."""
        return await self.get_climate(device)  # type: ignore[attr-defined]

    async def getMinTemperature(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_min_temperature."""
        return await self.get_min_temperature(device)  # type: ignore[attr-defined]

    async def getMaxTemperature(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_max_temperature."""
        return await self.get_max_temperature(device)  # type: ignore[attr-defined]

    async def getCurrentTemperature(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_current_temperature."""
        return await self.get_current_temperature(device)  # type: ignore[attr-defined]

    async def getTargetTemperature(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_target_temperature."""
        return await self.get_target_temperature(device)  # type: ignore[attr-defined]

    async def getMode(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_mode."""
        return await self.get_mode(device)  # type: ignore[attr-defined]

    async def getState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_state."""
        return await self.get_state(device)  # type: ignore[attr-defined]

    async def getCurrentOperation(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_current_operation."""
        return await self.get_current_operation(device)  # type: ignore[attr-defined]

    async def getBoostStatus(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_boost_status."""
        return await self.get_boost_status(device)  # type: ignore[attr-defined]

    async def getBoostTime(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_boost_time."""
        return await self.get_boost_time(device)  # type: ignore[attr-defined]

    async def getHeatOnDemand(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_heat_on_demand."""
        return await self.get_heat_on_demand(device)  # type: ignore[attr-defined]

    async def getOperationModes(self):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_operation_modes."""
        return await self.get_operation_modes()  # type: ignore[attr-defined]

    async def getScheduleNowNextLater(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_schedule_now_next_later."""
        return await self.get_schedule_now_next_later(device)  # type: ignore[attr-defined]

    async def minmaxTemperature(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for minmax_temperature."""
        return await self.minmax_temperature(device)  # type: ignore[attr-defined]


class LightCompatMixin:
    """CamelCase aliases for Light public methods."""

    async def turnOn(  # pylint: disable=invalid-name
        self, device: Device, brightness: int, color_temp: int, color: list
    ):
        """Backwards-compatible alias for turn_on."""
        return await self.turn_on(  # type: ignore[attr-defined]
            device, brightness, color_temp, color
        )

    async def turnOff(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for turn_off."""
        return await self.turn_off(device)  # type: ignore[attr-defined]

    async def getLight(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_light."""
        return await self.get_light(device)  # type: ignore[attr-defined]

    async def getState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_state."""
        return await self.get_state(device)  # type: ignore[attr-defined]

    async def getBrightness(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_brightness."""
        return await self.get_brightness(device)  # type: ignore[attr-defined]

    async def getMinColorTemp(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_min_color_temp."""
        return await self.get_min_color_temp(device)  # type: ignore[attr-defined]

    async def getMaxColorTemp(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_max_color_temp."""
        return await self.get_max_color_temp(device)  # type: ignore[attr-defined]

    async def getColorTemp(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_color_temp."""
        return await self.get_color_temp(device)  # type: ignore[attr-defined]

    async def getColor(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_color."""
        return await self.get_color(device)  # type: ignore[attr-defined]

    async def getColorMode(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_color_mode."""
        return await self.get_color_mode(device)  # type: ignore[attr-defined]


class SwitchCompatMixin:
    """CamelCase aliases for Switch (plug) public methods."""

    async def turnOn(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for turn_on."""
        return await self.turn_on(device)  # type: ignore[attr-defined]

    async def turnOff(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for turn_off."""
        return await self.turn_off(device)  # type: ignore[attr-defined]

    async def getSwitch(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_switch."""
        return await self.get_switch(device)  # type: ignore[attr-defined]

    async def getState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_state."""
        return await self.get_state(device)  # type: ignore[attr-defined]

    async def getPowerUsage(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_power_usage."""
        return await self.get_power_usage(device)  # type: ignore[attr-defined]

    async def getSwitchState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_switch_state."""
        return await self.get_switch_state(device)  # type: ignore[attr-defined]


class WaterHeaterCompatMixin:
    """CamelCase aliases for WaterHeater (hotwater) public methods."""

    async def get_boost(self, device: Device):
        """Alias for get_boost_status, used by the Hotwater_Boost sensor."""
        return await self.get_boost_status(device)  # type: ignore[attr-defined]

    async def getBoost(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_boost_status."""
        return await self.get_boost_status(device)  # type: ignore[attr-defined]

    async def getBoostTime(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_boost_time."""
        return await self.get_boost_time(device)  # type: ignore[attr-defined]

    async def setMode(self, device: Device, new_mode: str):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_mode."""
        return await self.set_mode(device, new_mode)  # type: ignore[attr-defined]

    async def setBoostOn(self, device: Device, mins: int):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_boost_on."""
        return await self.set_boost_on(device, mins)  # type: ignore[attr-defined]

    async def setBoostOff(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_boost_off."""
        return await self.set_boost_off(device)  # type: ignore[attr-defined]

    async def getWaterHeater(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_water_heater."""
        return await self.get_water_heater(device)  # type: ignore[attr-defined]

    async def getMode(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_mode."""
        return await self.get_mode(device)  # type: ignore[attr-defined]

    async def getState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_state."""
        return await self.get_state(device)  # type: ignore[attr-defined]

    async def getOperationModes(self):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_operation_modes."""
        return await self.get_operation_modes()  # type: ignore[attr-defined]

    async def getScheduleNowNextLater(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_schedule_now_next_later."""
        return await self.get_schedule_now_next_later(device)  # type: ignore[attr-defined]


class SensorCompatMixin:
    """CamelCase aliases for Sensor public methods."""

    async def getSensor(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_sensor."""
        return await self.get_sensor(device)  # type: ignore[attr-defined]

    async def getState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_state."""
        return await self.get_state(device)  # type: ignore[attr-defined]


class ActionCompatMixin:
    """CamelCase aliases for HiveAction public methods."""

    async def getAction(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_action."""
        return await self.get_action(device)  # type: ignore[attr-defined]

    async def setStatusOn(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_status_on."""
        return await self.set_status_on(device)  # type: ignore[attr-defined]

    async def setStatusOff(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for set_status_off."""
        return await self.set_status_off(device)  # type: ignore[attr-defined]

    async def getState(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_state."""
        return await self.get_state(device)  # type: ignore[attr-defined]


class HubCompatMixin:
    """CamelCase aliases for HiveHub public methods."""

    async def getSmokeStatus(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_smoke_status."""
        return await self.get_smoke_status(device)  # type: ignore[attr-defined]

    async def getDogBarkStatus(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_dog_bark_status."""
        return await self.get_dog_bark_status(device)  # type: ignore[attr-defined]

    async def getGlassBreakStatus(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for get_glass_break_status."""
        return await self.get_glass_break_status(device)  # type: ignore[attr-defined]


class SessionCompatMixin:
    """CamelCase and legacy aliases for HiveSession public methods."""

    device_list: Any  # provided by HiveSession.__init__

    @property
    def deviceList(self):  # pylint: disable=invalid-name
        """Backwards-compatible alias for device_list."""
        return self.device_list

    async def startSession(self, config: dict | None = None):  # pylint: disable=invalid-name
        """Backwards-compatible alias for start_session."""
        return await self.start_session(config)  # type: ignore[attr-defined]

    async def updateData(self, device: Device):  # pylint: disable=invalid-name
        """Backwards-compatible alias for update_data."""
        return await self.update_data(device)  # type: ignore[attr-defined]

    async def updateInterval(self, new_interval: int):  # pylint: disable=invalid-name
        """Backwards-compatible alias for Home Assistant Scan Interval."""
        self.config.scan_interval = timedelta(seconds=new_interval)  # type: ignore[attr-defined]
        return True
