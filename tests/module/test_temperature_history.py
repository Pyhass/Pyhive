"""Tests for Climate.get_temperature_history and the Hive history API call."""

# pylint: disable=too-few-public-methods
from unittest.mock import AsyncMock, MagicMock

from apyhiveapi.devices.heating import Climate
from apyhiveapi.helper.hive_exceptions import HiveApiError
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_HTTP_OK = 200
_ROWS = [
    {"date": "1792425280000", "temperature": 20.9375},
    {"date": "1792421680000", "temperature": 21.008695652173913},
]


def _make_climate(parsed=None, file_mode=False, raise_api_error=False):
    session = MagicMock()
    session.data = Map(
        {"products": {"heat-1": {"type": "heating", "state": {}}}, "devices": {}}
    )
    session.config = SessionConfig()
    session.config.file = file_mode
    session.api = MagicMock()
    if raise_api_error:
        session.api.get_heating_history = AsyncMock(side_effect=HiveApiError)
    else:
        session.api.get_heating_history = AsyncMock(
            return_value={"original": _HTTP_OK, "parsed": parsed}
        )
    device = Device(
        hive_id="heat-1",
        hive_name="Downstairs",
        hive_type="heating",
        ha_name="Downstairs",
        ha_type="climate",
        device_id="dev-1",
        device_name="Thermostat",
        device_data={},
    )
    return Climate(session), device, session


class TestGetTemperatureHistory:
    async def test_returns_sorted_rows_with_int_dates(self):
        climate, device, session = _make_climate({"data": _ROWS})
        history = await climate.get_temperature_history(device, 1, 2, "HOURS", 1)
        assert history == [
            {"date": 1792421680000, "temperature": 21.008695652173913},
            {"date": 1792425280000, "temperature": 20.9375},
        ]
        session.api.get_heating_history.assert_awaited_once_with(
            "heat-1", 1, 2, "HOURS", 1
        )

    async def test_defaults_to_hourly(self):
        climate, device, session = _make_climate({"data": []})
        assert await climate.get_temperature_history(device, 1, 2) == []
        session.api.get_heating_history.assert_awaited_once_with(
            "heat-1", 1, 2, "HOURS", 1
        )

    async def test_skips_malformed_rows(self):
        rows = [{"date": "x", "temperature": 1}, {"temperature": 2}, _ROWS[0]]
        climate, device, _ = _make_climate({"data": rows})
        history = await climate.get_temperature_history(device, 1, 2)
        assert history == [{"date": 1792425280000, "temperature": 20.9375}]

    async def test_empty_when_data_missing_or_not_a_list(self):
        for parsed in ({}, None, {"data": "nope"}, "garbage"):
            climate, device, _ = _make_climate(parsed)
            assert await climate.get_temperature_history(device, 1, 2) == []

    async def test_empty_on_api_error(self):
        climate, device, _ = _make_climate(raise_api_error=True)
        assert await climate.get_temperature_history(device, 1, 2) == []

    async def test_empty_in_file_mode_without_calling_api(self):
        climate, device, session = _make_climate(file_mode=True)
        assert await climate.get_temperature_history(device, 1, 2) == []
        session.api.get_heating_history.assert_not_awaited()

    async def test_camel_case_alias(self):
        climate, device, session = _make_climate({"data": _ROWS[:1]})
        history = await climate.getTemperatureHistory(device, 1, 2, "DAYS", 2)
        assert history == [{"date": 1792425280000, "temperature": 20.9375}]
        session.api.get_heating_history.assert_awaited_once_with(
            "heat-1", 1, 2, "DAYS", 2
        )
