"""Tests for the SNCF calendar."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from custom_components.sncf_trains.calendar import SNCFCalendar
from custom_components.sncf_trains.const import (
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
    CONF_TRAIN_COUNT,
)


def _fmt(moment: datetime) -> str:
    """Format a datetime the way the Navitia API does."""
    return moment.strftime("%Y%m%dT%H%M%S")


def _journey(
    dep: str = "20261109T070600",
    arr: str = "20261109T080100",
    base_arr: str = "20261109T080100",
    *,
    num: str = "860582",
    section_id: str | None = "section_1",
) -> dict:
    """Create a direct journey as returned by the SNCF API."""
    section = {
        "type": "public_transport",
        "base_departure_date_time": dep,
        "base_arrival_date_time": base_arr,
        "display_informations": {"trip_short_name": num},
    }
    if section_id is not None:
        section["id"] = section_id
    return {
        "departure_date_time": dep,
        "arrival_date_time": arr,
        "sections": [section],
    }


def _calendar(data: dict, *, train_count: int = 5) -> SNCFCalendar:
    subentry = MagicMock()
    subentry.data = {
        CONF_DEPARTURE_NAME: "Angerville",
        CONF_ARRIVAL_NAME: "Paris Austerlitz",
        CONF_TRAIN_COUNT: train_count,
    }
    coordinator = MagicMock()
    coordinator.entry.entry_id = "entry_1"
    coordinator.entry.subentries = {"sub1": subentry}
    coordinator.data = data
    coordinator.last_update_success = True
    return SNCFCalendar(coordinator)


# --- entity ------------------------------------------------------------------


def test_calendar_identity():
    calendar = _calendar({})
    assert calendar.unique_id == "calendar_sncf_train_entry_1"
    assert calendar.name == "Trains"
    assert ("sncf_trains", "entry_1") in calendar.device_info["identifiers"]


def test_calendar_without_journey_has_no_event():
    calendar = _calendar({"sub1": []})
    assert calendar.event is None
    assert calendar.extra_state_attributes == {}


# --- event conversion --------------------------------------------------------


def test_journey_is_converted_to_an_event():
    calendar = _calendar({"sub1": [_journey()]})

    (event,) = calendar._fetch_journeys()

    assert event.summary == "Angerville → Paris Austerlitz"
    assert event.location == "Angerville"
    assert event.uid == "section_1"
    assert event.train_num == 860582
    assert event.has_delay is False
    assert event.delay == 0
    assert event.start.strftime("%H:%M") == "07:06"
    assert event.end - event.start == timedelta(minutes=1)
    assert event.departure_date_time == event.start
    assert event.arrival_date_time.strftime("%H:%M") == "08:01"


def test_delayed_journey_is_flagged_in_the_summary():
    calendar = _calendar({"sub1": [_journey(arr="20261109T081100")]})

    (event,) = calendar._fetch_journeys()

    assert event.has_delay is True
    assert event.delay == 10
    assert event.summary == "Angerville → Paris Austerlitz - RETARD (10min)"
    assert "10 minutes" in event.description


def test_uid_falls_back_to_subentry_and_position():
    calendar = _calendar({"sub1": [_journey(section_id=None)]})
    (event,) = calendar._fetch_journeys()
    assert event.uid == "sub1_0"


def test_non_numeric_or_missing_train_number_gives_none():
    calendar = _calendar(
        {"sub1": [_journey(num="ABC"), _journey(num="", section_id="s2")]}
    )
    events = calendar._fetch_journeys()
    assert [event.train_num for event in events] == [None, None]


def test_invalid_journeys_are_skipped():
    no_section = {"departure_date_time": "20261109T070600", "sections": []}
    bad_dates = _journey(dep="bad", arr="bad")
    bad_first_section = _journey()
    bad_first_section["sections"] = ["oops"]
    calendar = _calendar(
        {"sub1": ["oops", no_section, bad_dates, bad_first_section, _journey()]},
    )

    events = calendar._fetch_journeys()

    assert len(events) == 1


def test_number_of_events_is_limited_by_train_count():
    journeys = [
        _journey(f"2026110907{minute:02d}00", section_id=f"s{minute}")
        for minute in range(3)
    ]
    calendar = _calendar({"sub1": journeys}, train_count=2)

    events = calendar._fetch_journeys()

    assert [event.uid for event in events] == ["s0", "s1"]


def test_unknown_subentries_and_bad_data_are_skipped():
    calendar = _calendar(
        {"unknown": [_journey()], "sub1": "oops"},
    )
    assert calendar._fetch_journeys() == []


# --- current / next event ----------------------------------------------------


def test_event_is_the_one_closest_to_now():
    now = datetime.now().replace(microsecond=0)
    past = _journey(_fmt(now - timedelta(hours=3)), section_id="past")
    soon = _journey(_fmt(now + timedelta(minutes=20)), section_id="soon")
    later = _journey(_fmt(now + timedelta(hours=3)), section_id="later")
    calendar = _calendar({"sub1": [past, later, soon]})

    assert calendar.event.uid == "soon"
    assert calendar.extra_state_attributes["number"] == 860582
    assert calendar.extra_state_attributes["has_delay"] is False
    assert calendar.extra_state_attributes["delay"] == 0
    assert calendar.extra_state_attributes["departure"] == calendar.event.start


def test_event_is_updated_when_the_coordinator_refreshes():
    calendar = _calendar({"sub1": []})
    assert calendar.event is None

    calendar.coordinator.data = {"sub1": [_journey(arr="20261109T081100")]}
    with patch.object(calendar, "async_write_ha_state") as write:
        calendar._handle_coordinator_update()

    write.assert_called_once()
    assert calendar.event is not None
    assert calendar.extra_state_attributes["has_delay"] is True
    assert calendar.extra_state_attributes["delay"] == 10

    calendar.coordinator.data = {"sub1": []}
    with patch.object(calendar, "async_write_ha_state"):
        calendar._handle_coordinator_update()

    assert calendar.event is None
    assert calendar.extra_state_attributes == {}


def test_event_is_hidden_while_the_coordinator_is_failing():
    calendar = _calendar({"sub1": [_journey()]})
    assert calendar.event is not None

    calendar.coordinator.last_update_success = False

    assert calendar.event is None


async def test_get_events_returns_all_journeys(hass):
    calendar = _calendar({"sub1": [_journey(), _journey("20261109T082300", section_id="s2")]})

    events = await calendar.async_get_events(
        hass, datetime(2026, 11, 9), datetime(2026, 11, 10)
    )

    assert [event.uid for event in events] == ["section_1", "s2"]


async def test_get_events_is_empty_while_the_coordinator_is_failing(hass):
    calendar = _calendar({"sub1": [_journey()]})
    calendar.coordinator.last_update_success = False

    assert (
        await calendar.async_get_events(
            hass, datetime(2026, 11, 9), datetime(2026, 11, 10)
        )
        == []
    )
