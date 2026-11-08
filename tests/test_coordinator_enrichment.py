"""Tests for the Gares & Connexions enrichment of the SNCF coordinator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntry
from homeassistant.util import dt as dt_util

from custom_components.sncf_trains.const import (
    CONF_API_KEY,
    CONF_FROM,
    CONF_OUTSIDE_INTERVAL,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_UPDATE_INTERVAL,
)
from custom_components.sncf_trains.coordinator import SncfUpdateCoordinator
from custom_components.sncf_trains.helpers import parse_datetime

STATION = "0087686006"
TIMETABLE_URL = f"https://www.garesetconnexions.sncf/schedule-table/Departures/{STATION}"
COURSE_URL = "https://live-portal-back.azurewebsites.net/api/course/87686006/circ-1"


def _create_entry(subentries: dict | None = None) -> MagicMock:
    entry = MagicMock(spec=ConfigEntry)
    entry.data = {CONF_API_KEY: "test_api_key"}
    entry.options = {CONF_UPDATE_INTERVAL: 2, CONF_OUTSIDE_INTERVAL: 60}
    entry.subentries = subentries or {}
    return entry


def _create_subentry() -> MagicMock:
    subentry = MagicMock()
    subentry.title = "Paris → Lyon"
    subentry.data = {
        CONF_FROM: "stop_area:dep",
        CONF_TO: "stop_area:arr",
        CONF_TIME_START: "07:00",
        CONF_TIME_END: "10:00",
    }
    return subentry


def _journey(
    *,
    num: str = "860582",
    dep: str = "20261109T070600",
    from_id: str = "stop_area:SNCF:87686006",
    to_id: str = "stop_area:SNCF:87391003",
) -> dict:
    return {
        "departure_date_time": dep,
        "arrival_date_time": "20261109T080100",
        "nb_transfers": 0,
        "sections": [
            {
                "type": "public_transport",
                "base_departure_date_time": dep,
                "base_arrival_date_time": "20261109T080100",
                "from": {"id": from_id},
                "to": {"id": to_id},
                "display_informations": {"trip_short_name": num},
            }
        ],
    }


def _timetable_item(**overrides) -> dict:
    item = {
        "trainNumber": "860582",
        "scheduledTime": "2026-11-09T07:06:00",
        "platform": {"track": "5"},
    }
    item.update(overrides)
    return item


def _course_detail() -> dict:
    return {
        "JourneyStop": [
            {
                "uic": "87686006",
                "scheduledTime": "2026-11-09T07:06:00",
                "platform": {"track": "B"},
            },
            {"uic": "87391003", "platform": {"track": "12"}},
        ],
        "composition": {"element": [{"numeroAffectation": "0SSCA-B85075"}]},
        "trainLength": 150,
    }


@pytest.fixture
def coordinator(hass, aioclient_mock) -> SncfUpdateCoordinator:
    return SncfUpdateCoordinator(hass, _create_entry())


# --- _train_number -----------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("860582", "860582"),
        ("0860582", "860582"),
        (" 86 05 82 ", "860582"),
        (860582, "860582"),
        ("000", "0"),
        ("", "0"),
        (None, "0"),
    ],
)
def test_train_number_normalisation(value, expected):
    assert SncfUpdateCoordinator._train_number(value) == expected


# --- _matching_departure -----------------------------------------------------


def test_departure_matches_within_twenty_minutes(hass):
    journey = _journey()
    match = SncfUpdateCoordinator._matching_departure

    assert match(journey, {"scheduledTime": "2026-11-09T07:06:00"}, STATION)
    assert match(journey, {"scheduledTime": "2026-11-09T07:26:00"}, STATION)
    assert match(journey, {"scheduledTime": "2026-11-09T06:46:00"}, STATION)
    assert not match(journey, {"scheduledTime": "2026-11-09T07:27:00"}, STATION)
    # Same hour, another day
    assert not match(journey, {"scheduledTime": "2026-11-10T07:06:00"}, STATION)


def test_departure_handles_utc_suffix(hass):
    journey = _journey()
    utc = dt_util.as_utc(parse_datetime("20261109T070600"))
    item = {"scheduledTime": utc.strftime("%Y-%m-%dT%H:%M:%SZ")}

    assert SncfUpdateCoordinator._matching_departure(journey, item, STATION)


def test_departure_uses_the_stop_of_the_selected_station(hass):
    journey = _journey()
    item = {
        "scheduledTime": "2026-11-09T05:00:00",  # terminus time, far from ours
        "JourneyStop": [
            {"uic": "87000000", "scheduledTime": "2026-11-09T05:00:00"},
            {"uic": "87686006", "scheduledTime": "2026-11-09T07:06:00"},
        ],
    }

    assert SncfUpdateCoordinator._matching_departure(journey, item, STATION)


def test_departure_uses_the_scheduled_not_the_real_time(hass):
    """A delayed train must still match its timetable entry."""
    journey = _journey(dep="20261109T071500")
    journey["sections"][0]["base_departure_date_time"] = "20261109T070600"

    assert SncfUpdateCoordinator._matching_departure(
        journey, {"scheduledTime": "2026-11-09T07:06:00"}, STATION
    )


def test_departure_without_public_transport_section_uses_journey_time(hass):
    journey = {"departure_date_time": "20261109T070600", "sections": []}

    assert SncfUpdateCoordinator._matching_departure(
        journey, {"scheduledTime": "2026-11-09T07:06:00"}, STATION
    )


@pytest.mark.parametrize("scheduled", [None, "", "not a date"])
def test_departure_with_unusable_timetable_time_does_not_match(hass, scheduled):
    assert not SncfUpdateCoordinator._matching_departure(
        _journey(), {"scheduledTime": scheduled}, STATION
    )


def test_departure_with_unusable_journey_time_does_not_match(hass):
    journey = {"departure_date_time": "", "sections": []}
    assert not SncfUpdateCoordinator._matching_departure(
        journey, {"scheduledTime": "2026-11-09T07:06:00"}, STATION
    )


# --- _enrich_journeys --------------------------------------------------------


async def test_platform_from_timetable_without_course_id(coordinator, aioclient_mock):
    aioclient_mock.get(TIMETABLE_URL, json=[_timetable_item()])
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "5"
    assert "train_cars" not in journey
    assert aioclient_mock.call_count == 1


async def test_leading_zeros_of_train_number_are_ignored(coordinator, aioclient_mock):
    aioclient_mock.get(TIMETABLE_URL, json=[_timetable_item(trainNumber="0860582")])
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "5"


async def test_course_details_add_platforms_and_composition(coordinator, aioclient_mock):
    aioclient_mock.get(
        TIMETABLE_URL, json=[_timetable_item(circulationId="circ-1")]
    )
    aioclient_mock.get(COURSE_URL, json=[_course_detail()])
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "B"
    assert journey["arrival_platform_track"] == "12"
    assert journey["train_units"] == 1
    assert journey["train_cars"] == 6
    assert journey["train_cars_source"] == "catalogue"
    assert journey["train_family"] == "Régiolis"
    assert journey["train_type"] == "Coradia Liner"
    assert journey["train_composition"] == ["0SSCA-B85075"]
    assert journey["train_length"] == 150


async def test_course_request_is_well_formed(coordinator, aioclient_mock):
    aioclient_mock.get(
        TIMETABLE_URL, json=[_timetable_item(circulationId="circ-1")]
    )
    aioclient_mock.get(COURSE_URL, json=[_course_detail()])

    await coordinator._enrich_journeys([_journey()], STATION)

    assert aioclient_mock.call_count == 2
    _, url, _, headers = aioclient_mock.mock_calls[-1]
    assert url.path.endswith("/api/course/87686006/circ-1")
    assert url.query["isDeparture"] == "true"
    assert headers["x-environment"] == "PROD"


async def test_course_is_requested_only_once_per_circulation(
    coordinator, aioclient_mock
):
    aioclient_mock.get(
        TIMETABLE_URL, json=[_timetable_item(circulationId="circ-1")]
    )
    aioclient_mock.get(COURSE_URL, json=[_course_detail()])
    first, second = _journey(), _journey()

    await coordinator._enrich_journeys([first, second], STATION)

    assert first["platform_track"] == second["platform_track"] == "B"
    assert aioclient_mock.call_count == 2  # timetable + a single course call


async def test_timetable_item_is_used_when_course_is_unavailable(
    coordinator, aioclient_mock
):
    aioclient_mock.get(
        TIMETABLE_URL, json=[_timetable_item(circulationId="circ-1")]
    )
    aioclient_mock.get(COURSE_URL, status=404)
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "5"
    assert "train_cars" not in journey
    assert "arrival_platform_track" not in journey


async def test_empty_course_payload_is_ignored(coordinator, aioclient_mock):
    aioclient_mock.get(
        TIMETABLE_URL, json=[_timetable_item(circulationId="circ-1")]
    )
    aioclient_mock.get(COURSE_URL, json=[])
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "5"
    assert "train_cars" not in journey


async def test_course_network_error_is_ignored(coordinator, aioclient_mock):
    aioclient_mock.get(
        TIMETABLE_URL, json=[_timetable_item(circulationId="circ-1")]
    )
    aioclient_mock.get(COURSE_URL, exc=TimeoutError())
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "5"


async def test_train_at_another_time_is_not_matched(coordinator, aioclient_mock):
    aioclient_mock.get(
        TIMETABLE_URL,
        json=[_timetable_item(scheduledTime="2026-11-09T12:00:00")],
    )
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert "platform_track" not in journey


async def test_second_candidate_is_used_when_the_first_does_not_match(
    coordinator, aioclient_mock
):
    """The same train number can run at several times of the day."""
    aioclient_mock.get(
        TIMETABLE_URL,
        json=[
            _timetable_item(scheduledTime="2026-11-09T12:00:00", platform={"track": "1"}),
            _timetable_item(platform={"track": "7"}),
        ],
    )
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "7"


async def test_unknown_train_number_is_left_untouched(coordinator, aioclient_mock):
    aioclient_mock.get(TIMETABLE_URL, json=[_timetable_item(trainNumber="111111")])
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert "platform_track" not in journey


async def test_timetable_http_error_is_ignored(coordinator, aioclient_mock):
    aioclient_mock.get(TIMETABLE_URL, status=500)
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert "platform_track" not in journey


async def test_unexpected_timetable_format_is_ignored(coordinator, aioclient_mock):
    aioclient_mock.get(TIMETABLE_URL, json={"error": "nope"})
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert "platform_track" not in journey


async def test_timetable_ignores_malformed_items(coordinator, aioclient_mock):
    aioclient_mock.get(TIMETABLE_URL, json=["oops", _timetable_item()])
    journey = _journey()

    await coordinator._enrich_journeys([journey], STATION)

    assert journey["platform_track"] == "5"


# --- boarding station resolution in _async_update_data -----------------------


async def _update(coordinator, journeys, enrich) -> dict:
    coordinator.entry.subentries = {"sub1": _create_subentry()}
    coordinator.api_client = MagicMock()
    coordinator.api_client.fetch_journeys = AsyncMock(return_value=journeys)
    with patch.object(coordinator, "_enrich_journeys", enrich):
        return await coordinator._async_update_data()


async def test_journeys_are_enriched_per_boarding_station(coordinator):
    at_first = _journey(from_id="stop_area:SNCF:87686006")
    also_at_first = _journey(num="860584", from_id="stop_point:OCE:SP:Train-87686006")
    at_second = _journey(num="860590", from_id="stop_area:SNCF:87391003")
    enrich = AsyncMock()

    await _update(coordinator, [at_first, also_at_first, at_second], enrich)

    calls = {call.args[1]: call.args[0] for call in enrich.await_args_list}
    assert set(calls) == {"0087686006", "0087391003"}
    assert calls["0087686006"] == [at_first, also_at_first]
    assert calls["0087391003"] == [at_second]


async def test_zero_padded_uic_is_resolved(coordinator):
    enrich = AsyncMock()

    await _update(coordinator, [_journey(from_id="stop_area:SNCF:0087686006")], enrich)

    assert enrich.await_args.args[1] == STATION


async def test_administrative_origin_without_uic_is_not_enriched(coordinator):
    enrich = AsyncMock()

    data = await _update(coordinator, [_journey(from_id="admin:fr:69123")], enrich)

    enrich.assert_not_awaited()
    assert len(data["sub1"]) == 1  # the journey itself is kept


async def test_journey_without_public_transport_section_is_not_enriched(coordinator):
    journey = _journey()
    journey["sections"] = [{"type": "crow_fly"}]
    enrich = AsyncMock()

    data = await _update(coordinator, [journey], enrich)

    enrich.assert_not_awaited()
    assert data["sub1"] == [journey]


async def test_enrichment_failure_does_not_break_the_update(coordinator):
    enrich = AsyncMock(side_effect=RuntimeError("G&C is down"))
    journey = _journey()

    data = await _update(coordinator, [journey], enrich)

    enrich.assert_awaited_once()
    assert data == {"sub1": [journey]}


async def test_no_enrichment_without_journeys(coordinator):
    enrich = AsyncMock()

    data = await _update(coordinator, [], enrich)

    enrich.assert_not_awaited()
    assert data == {"sub1": []}


# --- _async_setup ------------------------------------------------------------


async def test_async_setup_builds_the_api_client(coordinator):
    with patch(
        "custom_components.sncf_trains.coordinator.SncfApiClient"
    ) as client_class:
        await coordinator._async_setup()

    client_class.assert_called_once()
    assert client_class.call_args.args[1] == "test_api_key"
    assert coordinator.api_client is client_class.return_value
