"""Tests for the date, train number and disruption helpers."""

from custom_components.sncf_trains.helpers import (
    attach_disruptions,
    disruption_summary,
    format_time,
    get_duration,
    get_train_num,
    parse_datetime,
)


# --- parse_datetime / format_time / get_duration -----------------------------


def test_parse_datetime_navitia_format():
    parsed = parse_datetime("20261109T070600")
    assert parsed is not None
    assert (parsed.year, parsed.month, parsed.day) == (2026, 11, 9)
    assert (parsed.hour, parsed.minute) == (7, 6)
    assert parsed.tzinfo is not None


def test_parse_datetime_empty_or_invalid_returns_none():
    assert parse_datetime("") is None
    assert parse_datetime("not a date") is None
    assert parse_datetime("2026-13-45T99:99:99") is None


def test_format_time():
    assert format_time("20261109T070600") == "09/11/2026 - 07:06"


def test_format_time_invalid_is_not_available():
    assert format_time("") == "N/A"
    assert format_time("garbage") == "N/A"


def test_get_duration_in_minutes():
    journey = {
        "departure_date_time": "20261109T070600",
        "arrival_date_time": "20261109T080100",
    }
    assert get_duration(journey) == 55


def test_get_duration_missing_or_invalid_dates():
    assert get_duration({}) == 0
    assert get_duration({"departure_date_time": "20261109T070600"}) == 0
    assert (
        get_duration({"departure_date_time": "x", "arrival_date_time": "y"}) == 0
    )


# --- get_train_num -----------------------------------------------------------


def test_train_num_from_journey():
    assert get_train_num({"trip_short_name": 860582}) == "860582"


def test_train_num_from_public_transport_section():
    journey = {
        "sections": [
            {
                "type": "public_transport",
                "display_informations": {"trip_short_name": "860582"},
            }
        ]
    }
    assert get_train_num(journey) == "860582"


def test_train_num_prefers_public_transport_over_walking_section():
    journey = {
        "sections": [
            {"type": "crow_fly", "display_informations": {"num": "WALK"}},
            {"type": "public_transport", "display_informations": {"num": "6123"}},
        ]
    }
    assert get_train_num(journey) == "6123"


def test_train_num_falls_back_to_num_field():
    journey = {
        "sections": [
            {"type": "public_transport", "display_informations": {"num": "6123"}}
        ]
    }
    assert get_train_num(journey) == "6123"


def test_train_num_falls_back_to_any_section_for_old_format():
    journey = {"sections": [{"display_informations": {"trip_short_name": "4321"}}]}
    assert get_train_num(journey) == "4321"


def test_train_num_missing_returns_empty_string():
    assert get_train_num({}) == ""
    assert get_train_num({"sections": []}) == ""
    assert get_train_num({"sections": "oops"}) == ""
    assert get_train_num({"sections": [{"type": "public_transport"}]}) == ""


def test_train_num_ignores_malformed_sections():
    journey = {
        "sections": [
            "oops",
            {"type": "public_transport", "display_informations": "oops"},
            {"type": "public_transport", "display_informations": {"num": "77"}},
        ]
    }
    assert get_train_num(journey) == "77"


# --- attach_disruptions ------------------------------------------------------


def test_disruption_linked_from_section_links():
    journey = {"sections": [{"links": [{"type": "disruption", "id": "d1"}]}]}
    attach_disruptions([journey], [{"id": "d1"}])
    assert journey["disruptions"] == [{"id": "d1"}]


def test_disruption_linked_through_alternative_id_keys():
    journey = {
        "sections": [
            {
                "display_informations": {
                    "links": [
                        {"type": "disruption", "id": "impact-1"},
                        {"type": "disruption", "id": "dis-2"},
                    ]
                }
            }
        ]
    }
    attach_disruptions(
        [journey],
        [{"impact_id": "impact-1"}, {"disruption_id": "dis-2"}],
    )
    assert journey["disruptions"] == [
        {"impact_id": "impact-1"},
        {"disruption_id": "dis-2"},
    ]


def test_disruption_is_not_duplicated():
    link = {"type": "disruption", "id": "d1"}
    journey = {
        "sections": [
            {"links": [link], "display_informations": {"links": [link]}},
            {"links": [link]},
        ]
    }
    attach_disruptions([journey], [{"id": "d1"}])
    assert journey["disruptions"] == [{"id": "d1"}]


def test_unknown_or_non_disruption_links_are_ignored():
    journey = {
        "sections": [
            {
                "links": [
                    {"type": "disruption", "id": "unknown"},
                    {"type": "line", "id": "d1"},
                    "oops",
                ]
            }
        ]
    }
    attach_disruptions([journey], [{"id": "d1"}])
    assert journey["disruptions"] == []


def test_attach_disruptions_tolerates_malformed_input():
    journeys = ["oops", {"sections": None}, {"sections": ["oops"]}]
    attach_disruptions(journeys, ["oops", {"id": "d1"}])
    assert journeys[0] == "oops"
    assert journeys[1]["disruptions"] == []
    assert journeys[2]["disruptions"] == []


# --- disruption_summary ------------------------------------------------------

EMPTY_SUMMARY = {
    "disruption_cause": None,
    "disruption_effect": None,
    "disruption_message": None,
}


def test_summary_without_disruption():
    assert disruption_summary({}) == EMPTY_SUMMARY
    assert disruption_summary({"disruptions": []}) == EMPTY_SUMMARY


def test_summary_uses_top_level_cause_first():
    journey = {
        "disruptions": [
            {
                "cause": "Panne de signalisation",
                "severity": {"effect": "NO_SERVICE"},
                "messages": [{"text": "Train supprimé"}],
                "impacted_objects": [
                    {"impacted_stops": [{"cause": "Autre cause"}]}
                ],
            }
        ]
    }
    assert disruption_summary(journey) == {
        "disruption_cause": "Panne de signalisation",
        "disruption_effect": "NO_SERVICE",
        "disruption_message": "Train supprimé",
    }


def test_summary_without_message_or_severity():
    journey = {"disruptions": [{"cause": "Travaux"}]}
    assert disruption_summary(journey) == {
        "disruption_cause": "Travaux",
        "disruption_effect": None,
        "disruption_message": None,
    }


def test_summary_only_describes_the_main_disruption():
    journey = {
        "disruptions": [
            {"cause": "Première", "severity": {"effect": "REDUCED_SERVICE"}},
            {"cause": "Seconde", "severity": {"effect": "NO_SERVICE"}},
        ]
    }
    summary = disruption_summary(journey)
    assert summary["disruption_cause"] == "Première"
    assert summary["disruption_effect"] == "REDUCED_SERVICE"
