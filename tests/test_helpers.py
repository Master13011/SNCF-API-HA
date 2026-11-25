"""Tests for disruption and composition helpers."""

from custom_components.sncf_trains.helpers import (
    attach_disruptions,
    disruption_summary,
)
from custom_components.sncf_trains.rolling_stock import analyser_composition


def test_attach_and_summarize_disruption():
    journey = {"sections": [{"display_informations": {
        "links": [{"type": "disruption", "id": "d1"}]}}]}
    attach_disruptions([journey], [{
        "id": "d1",
        "severity": {"effect": "SIGNIFICANT_DELAYS"},
        "messages": [{"text": "Trafic perturbe"}],
        "impacted_objects": [{"impacted_stops": [
            {"cause": ""}, {"cause": "Sortie tardive du depot"}]}],
    }])
    assert disruption_summary(journey) == {
        "disruption_cause": "Sortie tardive du depot",
        "disruption_effect": "SIGNIFICANT_DELAYS",
        "disruption_message": "Trafic perturbe",
    }


def test_no_disruption():
    journey = {"sections": []}
    attach_disruptions([journey], [])
    assert disruption_summary(journey)["disruption_cause"] is None


def test_repeated_trainset_counted_once():
    result = analyser_composition(
        [{"numeroAffectation": "0SSCA-B85075"}] * 4
    )
    assert result["train_units"] == 1
    assert result["train_cars"] == 6


def test_two_distinct_trainsets():
    result = analyser_composition([
        {"numeroAffectation": "0SSCA-B85075"},
        {"numeroAffectation": "0SSCA-B85077"},
    ])
    assert result["train_units"] == 2
    assert result["train_cars"] == 12


def test_get_stop_uic_from_codes_new_netex_ids():
    from custom_components.sncf_trains.helpers import get_stop_uic

    place = {
        "id": "stop_point:SNC:VSP:FR::LMU:6c1a3b10-cb0a-11e8-8bfa-f784c1c7c611:",
        "stop_point": {
            "id": "stop_point:SNC:VSP:FR::LMU:6c1a3b10-cb0a-11e8-8bfa-f784c1c7c611:",
            "codes": [
                {"type": "UIC", "value": "87756056"},
                {"type": "source", "value": "FR::LMU:6c1a3b10:"},
            ],
        },
    }
    assert get_stop_uic(place) == "87756056"


def test_get_stop_uic_legacy_id_and_missing():
    from custom_components.sncf_trains.helpers import get_stop_uic

    assert get_stop_uic({"id": "stop_point:SNCF:87756056:Train"}) == "87756056"
    assert get_stop_uic({"id": "stop_point:SNC:VSP:FR::LMU:6c1a3b10-cb0a-11e8:"}) is None
    assert get_stop_uic(None) is None
