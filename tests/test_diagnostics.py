"""Tests for the SNCF diagnostics."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from homeassistant.components.diagnostics import REDACTED

from custom_components.sncf_trains.const import (
    CONF_API_KEY,
    CONF_FROM,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
)
from custom_components.sncf_trains.diagnostics import (
    async_get_config_entry_diagnostics,
)


def _journey(num: str = "860582") -> dict:
    return {
        "departure_date_time": "20261109T070600",
        "arrival_date_time": "20261109T080100",
        "requested_date_time": "20261109T070000",
        "duration": 3300,
        "nb_transfers": 0,
        "type": "best",
        "status": "SIGNIFICANT_DELAYS",
        "tags": ["tag"],
        "sections": [
            {
                "id": "section_1",
                "type": "public_transport",
                "mode": "train",
                "departure_date_time": "20261109T070600",
                "arrival_date_time": "20261109T080100",
                "duration": 3300,
                "display_informations": {
                    "commercial_mode": "TER",
                    "physical_mode": "Train",
                    "direction": "Paris",
                    "trip_short_name": num,
                    "num": "9999",
                },
            }
        ],
    }


def _entry(journeys_by_subentry: dict, *, subentry_ids=("sub1",)) -> MagicMock:
    entry = MagicMock()
    entry.title = "Trains SNCF"
    entry.entry_id = "entry_1"
    entry.version = 1
    entry.data = {CONF_API_KEY: "super-secret", "other": "visible"}
    entry.options = {CONF_API_KEY: "also-secret", "update_interval": 2}

    subentries = {}
    for subentry_id in subentry_ids:
        subentry = MagicMock()
        subentry.title = f"Trajet {subentry_id}"
        subentry.data = {
            CONF_FROM: "stop_area:dep",
            CONF_TO: "stop_area:arr",
            CONF_TIME_START: "07:00",
            CONF_TIME_END: "10:00",
        }
        subentries[subentry_id] = subentry
    entry.subentries = subentries

    coordinator = MagicMock()
    coordinator.data = journeys_by_subentry
    coordinator.last_update_success = True
    coordinator.last_update_success_time = datetime(2026, 11, 9, 7, 0, 0)
    coordinator.update_interval = timedelta(minutes=2)
    coordinator.update_interval_minutes = 2
    coordinator.outside_interval_minutes = 60
    entry.runtime_data = coordinator
    return entry


async def test_api_key_is_redacted(hass):
    entry = _entry({"sub1": [_journey()]})

    result = await async_get_config_entry_diagnostics(hass, entry)

    config = result["config_entry"]
    assert config["data"][CONF_API_KEY] == REDACTED
    assert config["options"][CONF_API_KEY] == REDACTED
    assert config["data"]["other"] == "visible"
    assert config["options"]["update_interval"] == 2
    assert config["title"] == "Trains SNCF"
    assert config["entry_id"] == "entry_1"
    assert config["version"] == 1
    assert "super-secret" not in str(result)
    assert "also-secret" not in str(result)


async def test_coordinator_information(hass):
    entry = _entry({"sub1": [_journey()]})

    coordinator = (await async_get_config_entry_diagnostics(hass, entry))[
        "coordinator"
    ]

    assert coordinator["available"] is True
    assert coordinator["last_update_success"] is True
    assert coordinator["last_update_time"] == "2026-11-09 07:00:00"
    assert coordinator["update_interval"] == "0:02:00"
    assert coordinator["update_interval_minutes"] == 2
    assert coordinator["outside_interval_minutes"] == 60
    assert coordinator["subentries_count"] == 1
    assert coordinator["data_subentries_count"] == 1


async def test_subentry_and_journey_details(hass):
    entry = _entry({"sub1": [_journey()]})

    result = await async_get_config_entry_diagnostics(hass, entry)

    subentry = result["subentries"]["sub1"]
    assert subentry["title"] == "Trajet sub1"
    assert subentry["departure"] == "stop_area:dep"
    assert subentry["arrival"] == "stop_area:arr"
    assert subentry["time_start"] == "07:00"
    assert subentry["time_end"] == "10:00"
    assert subentry["journeys_count"] == 1

    (journey,) = subentry["journeys"]
    assert journey["index"] == 0
    assert journey["train_num"] == "860582"
    assert journey["departure_date_time"] == "20261109T070600"
    assert journey["nb_transfers"] == 0
    assert journey["status"] == "SIGNIFICANT_DELAYS"
    assert journey["sections_count"] == 1

    (section,) = journey["sections"]
    assert section["id"] == "section_1"
    assert section["type"] == "public_transport"
    assert section["display_informations"] == {
        "commercial_mode": "TER",
        "physical_mode": "Train",
        "direction": "Paris",
        "trip_short_name": "860582",
        "num": "9999",
    }


async def test_journeys_are_limited_to_ten_but_counted_entirely(hass):
    entry = _entry({"sub1": [_journey(str(n)) for n in range(12)]})

    subentry = (await async_get_config_entry_diagnostics(hass, entry))[
        "subentries"
    ]["sub1"]

    assert subentry["journeys_count"] == 12
    assert len(subentry["journeys"]) == 10


async def test_invalid_journeys_and_sections_are_flagged(hass):
    broken_section = _journey()
    broken_section["sections"] = ["oops"]
    entry = _entry({"sub1": ["oops", broken_section]})

    journeys = (await async_get_config_entry_diagnostics(hass, entry))[
        "subentries"
    ]["sub1"]["journeys"]

    assert journeys[0] == {"index": 0, "invalid": True, "value_type": "str"}
    assert journeys[1]["sections"] == [
        {"index": 0, "invalid": True, "value_type": "str"}
    ]


async def test_non_list_sections_are_treated_as_empty(hass):
    journey = _journey()
    journey["sections"] = "oops"
    entry = _entry({"sub1": [journey]})

    (info,) = (await async_get_config_entry_diagnostics(hass, entry))["subentries"][
        "sub1"
    ]["journeys"]

    assert info["sections_count"] == 0
    assert info["sections"] == []


async def test_subentry_without_data_or_with_bad_data(hass):
    entry = _entry({"sub2": "oops"}, subentry_ids=("sub1", "sub2"))

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["subentries"]["sub1"]["journeys_count"] == 0
    assert result["subentries"]["sub2"]["journeys_count"] == 0
    assert result["coordinator"]["subentries_count"] == 2


async def test_missing_coordinator(hass):
    entry = _entry({})
    entry.runtime_data = None

    result = await async_get_config_entry_diagnostics(hass, entry)

    assert result["coordinator"] == {
        "available": False,
        "reason": "Coordinator non disponible",
    }
    assert "subentries" not in result
    assert result["config_entry"]["data"][CONF_API_KEY] == REDACTED
