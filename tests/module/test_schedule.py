"""Tests for ScheduleMixin — weekly schedule get/set shared by heating and hot water."""

# pylint: disable=too-few-public-methods
import copy
from unittest.mock import AsyncMock, MagicMock

import pytest
from apyhiveapi.devices.heating import Climate
from apyhiveapi.devices.hotwater import WaterHeater
from apyhiveapi.devices.schedule import DAYS
from apyhiveapi.helper.hivedataclasses import Device, SessionConfig
from apyhiveapi.helper.map import Map

_HTTP_OK = 200
_HTTP_BAD = 400
_NEW_TARGET = 19.5


def _heating_week(target_a=20, target_b=7):
    """A minimal valid heating schedule with two slots per day."""
    return {
        day: [
            {"start": 420, "value": {"target": target_a}},
            {"start": 1320, "value": {"target": target_b}},
        ]
        for day in DAYS
    }


def _hotwater_week():
    """A minimal valid hot water schedule with two slots per day."""
    return {
        day: [
            {"start": 405, "value": {"status": "ON"}},
            {"start": 435, "value": {"status": "OFF"}},
        ]
        for day in DAYS
    }


def _make_session(products):
    session = MagicMock()
    session.data = Map(
        {"products": products, "devices": {}, "actions": {}, "minMax": {}, "user": {}}
    )
    session.config = SessionConfig()
    session.helper = MagicMock()
    session.attr = MagicMock()
    session.attr.online_offline = AsyncMock(return_value=True)
    session.api = MagicMock()
    session.api.set_state = AsyncMock(return_value={"original": _HTTP_OK, "parsed": {}})
    session.hive_refresh_tokens = AsyncMock()
    session.get_devices = AsyncMock(return_value=True)
    return session


def _make_climate(schedule=None, product_type="heating"):
    """Climate whose product carries *schedule*; get_devices leaves it unchanged."""
    products = {"heat-1": {"type": product_type, "state": {}}}
    if schedule is not None:
        products["heat-1"]["state"]["schedule"] = schedule
    return Climate(session=_make_session(products))


def _make_hotwater(schedule=None):
    products = {"hw-1": {"type": "hotwater", "state": {"schedule": schedule}}}
    return WaterHeater(session=_make_session(products))


def _device(hive_id="heat-1", ha_type="climate", online=True):
    return Device(
        hive_id=hive_id,
        hive_name="Zone",
        hive_type="heating",
        ha_type=ha_type,
        device_id="dev-1",
        device_name="Zone",
        device_data={"online": online},
        ha_name="Zone",
    )


def _simulate_hive_storing(climate, hive_id="heat-1"):
    """Make get_devices copy the posted schedule into the product, as Hive does."""

    async def _store(_id):
        _, kwargs = climate.session.api.set_state.call_args
        climate.session.data.products[hive_id]["state"]["schedule"] = copy.deepcopy(
            kwargs["schedule"]
        )
        return True

    climate.session.get_devices = AsyncMock(side_effect=_store)


class TestGetSchedule:
    """get_schedule returns an editable deep copy of the stored week."""

    async def test_returns_copy_of_stored_schedule(self):
        """The returned dict equals the stored one but shares no slot objects."""
        week = _heating_week()
        climate = _make_climate(week)
        result = await climate.get_schedule(_device())
        assert result == week
        result["monday"][0]["value"]["target"] = 99
        assert week["monday"][0]["value"]["target"] != 99  # noqa: PLR2004

    async def test_returns_none_when_missing(self):
        """No schedule in product state yields None rather than an error."""
        climate = _make_climate()
        assert await climate.get_schedule(_device()) is None

    async def test_returns_none_for_unknown_product(self):
        """A device not present in session.data.products yields None."""
        climate = _make_climate(_heating_week())
        assert await climate.get_schedule(_device(hive_id="nope")) is None


class TestSetScheduleHeating:
    """set_schedule posts the whole normalised week and verifies it stuck."""

    async def test_posts_full_week_and_returns_true(self):
        """Happy path: set_state gets schedule=<week>, stored copy matches."""
        climate = _make_climate(_heating_week())
        _simulate_hive_storing(climate)
        new = _heating_week()
        new["monday"][0]["value"]["target"] = _NEW_TARGET

        assert await climate.set_schedule(_device(), new) is True

        climate.session.api.set_state.assert_called_once()
        args, kwargs = climate.session.api.set_state.call_args
        assert args == ("heating", "heat-1")
        assert list(kwargs) == ["schedule"]
        assert kwargs["schedule"]["monday"][0]["value"]["target"] == _NEW_TARGET
        assert set(kwargs["schedule"]) == set(DAYS)

    async def test_strips_extra_slot_keys_and_sorts(self):
        """Keys the Hive web app adds (type/dayIndex/eventIndex) are dropped."""
        climate = _make_climate(_heating_week())
        _simulate_hive_storing(climate)
        new = _heating_week()
        new["monday"] = [
            {
                "start": 1320,
                "value": {"target": 7, "junk": 1},
                "type": "HEATING",
                "dayIndex": 0,
                "eventIndex": 1,
            },
            {"start": 420, "value": {"target": 20}},
        ]

        assert await climate.set_schedule(_device(), new) is True
        _, kwargs = climate.session.api.set_state.call_args
        assert kwargs["schedule"]["monday"] == [
            {"start": 420, "value": {"target": 20}},
            {"start": 1320, "value": {"target": 7}},
        ]

    async def test_trvcontrol_supported(self):
        """TRV zones use the same target-based slots as heating."""
        climate = _make_climate(_heating_week(), product_type="trvcontrol")
        _simulate_hive_storing(climate)
        assert await climate.set_schedule(_device(), _heating_week()) is True

    async def test_returns_false_when_api_fails(self):
        """A non-200 from set_state propagates as False with no verify step."""
        climate = _make_climate(_heating_week())
        climate.session.api.set_state = AsyncMock(
            return_value={"original": _HTTP_BAD, "parsed": {}}
        )
        assert await climate.set_schedule(_device(), _heating_week(9, 9)) is False
        climate.session.get_devices.assert_not_called()

    async def test_returns_false_when_offline(self):
        """Offline devices short-circuit before any API call."""
        climate = _make_climate(_heating_week())
        assert (
            await climate.set_schedule(_device(online=False), _heating_week()) is False
        )
        climate.session.api.set_state.assert_not_called()

    async def test_returns_false_when_hive_silently_ignores(self):
        """Hive answers 200 but the refreshed product still has the old week."""
        climate = _make_climate(_heating_week())  # get_devices is a no-op
        assert await climate.set_schedule(_device(), _heating_week(9, 9)) is False
        climate.session.api.set_state.assert_called_once()

    async def test_returns_false_for_unsupported_product_type(self):
        """Products with no schedule concept are refused without an API call."""
        climate = _make_climate(_heating_week(), product_type="activeplug")
        assert await climate.set_schedule(_device(), _heating_week()) is False
        climate.session.api.set_state.assert_not_called()

    async def test_returns_false_for_unknown_product(self):
        """A device absent from session.data.products is refused."""
        climate = _make_climate(_heating_week())
        assert (
            await climate.set_schedule(_device(hive_id="nope"), _heating_week())
            is False
        )


class TestSetScheduleHotwater:
    """Hot water slots use {"status": "ON"|"OFF"} values."""

    async def test_posts_status_slots(self):
        """Hot water schedule is posted under the hotwater product type."""
        heater = _make_hotwater(_hotwater_week())
        _simulate_hive_storing(heater, hive_id="hw-1")
        new = _hotwater_week()
        new["sunday"][0]["value"]["status"] = "OFF"
        dev = _device(hive_id="hw-1", ha_type="water_heater")

        assert await heater.set_schedule(dev, new) is True
        args, kwargs = heater.session.api.set_state.call_args
        assert args == ("hotwater", "hw-1")
        assert kwargs["schedule"]["sunday"][0]["value"] == {"status": "OFF"}

    async def test_rejects_heating_style_slots(self):
        """A target-based slot on a hot water product is a caller error."""
        heater = _make_hotwater(_hotwater_week())
        dev = _device(hive_id="hw-1", ha_type="water_heater")
        with pytest.raises(ValueError, match="'status'"):
            await heater.set_schedule(dev, _heating_week())


class TestSetScheduleValidation:
    """Malformed schedules raise ValueError before anything is posted."""

    @pytest.mark.parametrize(
        ("mutate", "match"),
        [
            (lambda w: w.pop("sunday"), "missing=\\['sunday'\\]"),
            (lambda w: w.update(funday=[]), "unknown=\\['funday'\\]"),
            (lambda w: w.__setitem__("monday", []), "non-empty list"),
            (lambda w: w.__setitem__("monday", "0900"), "non-empty list"),
            (lambda w: w.__setitem__("monday", ["slot"]), "must be a dict"),
            (lambda w: w["monday"][0].__setitem__("start", 1440), "0..1439"),
            (lambda w: w["monday"][0].__setitem__("start", -1), "0..1439"),
            (lambda w: w["monday"][0].__setitem__("start", "420"), "0..1439"),
            (lambda w: w["monday"][0].__setitem__("start", True), "0..1439"),
            (lambda w: w["monday"][0].__setitem__("value", {"temp": 20}), "'target'"),
            (lambda w: w["monday"][0].__setitem__("value", 20), "'target'"),
            (lambda w: w["monday"][1].__setitem__("start", 420), "duplicate"),
        ],
    )
    async def test_rejects_malformed(self, mutate, match):
        """Each mutation produces a ValueError naming the problem."""
        climate = _make_climate(_heating_week())
        week = _heating_week()
        mutate(week)
        with pytest.raises(ValueError, match=match):
            await climate.set_schedule(_device(), week)
        climate.session.api.set_state.assert_not_called()

    async def test_rejects_non_dict(self):
        """A list instead of a dict is rejected."""
        climate = _make_climate(_heating_week())
        with pytest.raises(ValueError, match="keyed by weekday"):
            await climate.set_schedule(_device(), [])


class TestCamelCaseAliases:
    """getSchedule / setSchedule delegate for HA custom-component compatibility."""

    async def test_aliases_delegate(self):
        """Both aliases exist on Climate and WaterHeater and delegate."""
        for handler in (
            _make_climate(_heating_week()),
            _make_hotwater(_hotwater_week()),
        ):
            handler.get_schedule = AsyncMock(return_value="week")
            handler.set_schedule = AsyncMock(return_value=True)
            dev = _device()
            assert await handler.getSchedule(dev) == "week"
            assert await handler.setSchedule(dev, {"x": 1}) is True
            handler.set_schedule.assert_called_once_with(dev, {"x": 1})


class TestFileModeRoundTrip:
    """The bundled fixture's heating and hot water schedules pass validation."""

    async def test_fixture_schedules_normalise_cleanly(self):
        """get_schedule output from the fixture is accepted by the validator."""
        from apyhiveapi import Hive  # pylint: disable=import-outside-toplevel

        async with Hive(username="use@file.com", password="x") as hive:
            await hive.start_session({})
            for dev in hive.device_list["climate"]:
                week = await hive.heating.get_schedule(dev)
                assert set(week) == set(DAYS)
                assert hive.heating._normalise_schedule(week, "target") == week  # pylint: disable=protected-access
            for dev in hive.device_list["water_heater"]:
                week = await hive.hotwater.get_schedule(dev)
                assert hive.hotwater._normalise_schedule(week, "status") == week  # pylint: disable=protected-access
