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


def test_get_stop_uic_monaco_fallback():
    from custom_components.sncf_trains.helpers import get_stop_uic

    place = {
        "id": "stop_point:SNC:VSP:FR::LMO:91653280-cb0a-11e8-8bfa-f784c1c7c611:",
        "name": "Monaco-Monte-Carlo (Monaco)",
        "stop_point": {
            "id": "stop_point:SNC:VSP:FR::LMO:91653280-cb0a-11e8-8bfa-f784c1c7c611:",
            "name": "Monaco-Monte-Carlo",
            "codes": [{"type": "source", "value": "FR::LMO:91653280:"}],
        },
    }
    assert get_stop_uic(place) == "87756403"
    assert get_stop_uic({"name": "Monaco-Monte-Carlo (Monaco)"}) == "87756403"


def test_get_stop_uic_ignores_uuid_digits():
    from custom_components.sncf_trains.helpers import get_stop_uic

    assert get_stop_uic(
        {"id": "stop_point:SNC:VSP:FR::LMU:69967660-cb0a-11e8-8bfa-f784c1c7c611:"}
    ) is None


def test_get_stop_uic_ventimiglia_fallback():
    from custom_components.sncf_trains.helpers import get_stop_uic

    assert get_stop_uic({"name": "Ventimiglia (Ventimiglia)"}) == "83045013"
    assert get_stop_uic({"stop_point": {"name": "Vintimille"}}) == "83045013"


def test_get_stop_uic_border_stations_by_name():
    from custom_components.sncf_trains.helpers import get_stop_uic

    assert get_stop_uic({"name": "Genève-Cornavin (Genève)"}) == "85010082"
    assert get_stop_uic({"name": "Basel SBB"}) == "85000109"
    assert get_stop_uic({"name": "Bâle SBB (Bâle)"}) == "85000109"
    assert get_stop_uic({"name": "Basel St. Johann"}) == "87187930"
    assert get_stop_uic({"name": "Nice-Ville (Nice)"}) is None


def test_get_stop_uic_legacy_ids_with_prefix():
    from custom_components.sncf_trains.helpers import get_stop_uic

    assert get_stop_uic({"id": "stop_point:OCE:SP:Train-87686006"}) == "87686006"
    assert get_stop_uic({"id": "stop_area:SNCF:87391003"}) == "87391003"
