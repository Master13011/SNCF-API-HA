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
