"""Tests for the rolling stock identification."""

import pytest

from custom_components.sncf_trains.rolling_stock import (
    analyser_composition,
    identifier_materiel,
)


# --- identifier_materiel -----------------------------------------------------


def test_known_trainset_with_fixed_length():
    result = identifier_materiel("B85075")
    assert result == {
        "reference": "B85075",
        "type": "Coradia Liner",
        "famille": "Régiolis",
        "voitures": 6,
        "source": "catalogue",
    }


def test_operator_prefix_is_ignored():
    result = identifier_materiel("0SSCA-B85075")
    assert result is not None
    assert result["reference"] == "B85075"
    assert result["voitures"] == 6


def test_series_without_stable_length_has_no_car_count():
    """Z 24500 exists in several lengths: the count must not be guessed."""
    result = identifier_materiel("0KSRA-Z24595")
    assert result is not None
    assert result["type"] == "TER 2N NG"
    assert result["voitures"] is None
    assert result["source"] == "inconnue"


def test_spaces_and_case_are_tolerated():
    result = identifier_materiel("  z 20950 ")
    assert result is not None
    assert result["reference"] == "Z20950"
    assert result["type"] == "Z 2N"
    assert result["voitures"] == 4


@pytest.mark.parametrize(
    ("reference", "cars"),
    [
        ("Z51500M", 4),
        ("Z51500L", 6),
        ("Z51500", None),
    ],
)
def test_regiolis_variant_is_read_only_when_explicit(reference, cars):
    result = identifier_materiel(reference)
    assert result is not None
    assert result["famille"] == "Régiolis"
    assert result["voitures"] == cars


@pytest.mark.parametrize(
    ("reference", "name", "cars"),
    [
        ("TGV ATLANTIQUE 325", "TGV Atlantique", 10),
        ("tgv duplex 233", "TGV Duplex", 8),
        ("TGV RÉSEAU 501", "TGV Réseau", 8),
        ("TGV M 912", "TGV M", None),
    ],
)
def test_explicit_tgv_families(reference, name, cars):
    result = identifier_materiel(reference)
    assert result is not None
    assert result["famille"] == "TGV"
    assert result["type"] == name
    assert result["voitures"] == cars
    assert result["source"] == ("catalogue" if cars is not None else "inconnue")


def test_locomotive_has_no_car_count():
    result = identifier_materiel("BB26001")
    assert result is not None
    assert result["famille"] == "Locomotive"
    assert result["voitures"] is None


@pytest.mark.parametrize(
    "reference",
    [
        "",
        "INCONNU",
        "87686006",  # a bare UIC code is not a trainset reference
        "Z99999",  # out of every known range
        "AB85075",  # letters glued to the prefix
        "B850750",  # too many digits
    ],
)
def test_unknown_references_return_none(reference):
    assert identifier_materiel(reference) is None


# --- analyser_composition ----------------------------------------------------


def _elements(*references):
    return [{"numeroAffectation": reference} for reference in references]


def test_single_trainset():
    result = analyser_composition(_elements("0SSCA-B85075"))
    assert result["train_units"] == 1
    assert result["train_cars"] == 6
    assert result["train_cars_source"] == "catalogue"
    assert result["train_family"] == "Régiolis"
    assert result["train_type"] == "Coradia Liner"
    assert result["train_composition"] == ["0SSCA-B85075"]


def test_coupled_trainsets_of_the_same_type_are_summed():
    result = analyser_composition(_elements("B85075", "B85077"))
    assert result["train_units"] == 2
    assert result["train_cars"] == 12
    assert result["train_family"] == "Régiolis"
    assert result["train_type"] == "Coradia Liner"


def test_mixed_trainsets_have_no_single_family_or_type():
    result = analyser_composition(_elements("B85075", "Z20950"))
    assert result["train_units"] == 2
    assert result["train_cars"] == 10
    assert result["train_family"] is None
    assert result["train_type"] is None


def test_unknown_trainset_makes_the_whole_composition_unknown():
    result = analyser_composition(_elements("B85075", "INCONNU"))
    assert result["train_units"] is None
    assert result["train_cars"] is None
    assert result["train_cars_source"] == "inconnue"
    assert result["train_family"] is None


def test_trainset_without_catalogue_length_gives_no_car_total():
    result = analyser_composition(_elements("B85075", "Z24595"))
    assert result["train_units"] == 2
    assert result["train_cars"] is None
    assert result["train_cars_source"] == "inconnue"


def test_locomotive_is_not_counted_as_a_trainset():
    result = analyser_composition(_elements("BB26001"))
    assert result["train_units"] is None
    assert result["train_cars"] is None


def test_element_without_assignment_number_invalidates_the_result():
    result = analyser_composition([{"numeroAffectation": "B85075"}, {}])
    assert result["train_composition"] == ["B85075"]
    assert result["train_units"] is None
    assert result["train_cars"] is None


def test_invalid_elements_are_ignored():
    result = analyser_composition(["not a dict", {"numeroAffectation": "B85075"}])
    assert result["train_composition"] == ["B85075"]
    assert result["train_cars"] is None


@pytest.mark.parametrize("number", ["22313", "22355"])
def test_locomotive_without_separator(number):
    result = identifier_materiel(f"0KSRABB{number}")
    assert result is not None
    assert result["reference"] == f"BB{number}"
    assert result["type"] == "Locomotive BB 22200"
    assert result["voitures"] is None


@pytest.mark.parametrize(
    "references",
    [
        ("0KSRABB22313", "0KCBYLGC722N", "0KCBYLJH787L"),
        ("0KCBYLJH787U", "0KSRABB22355"),
    ],
)
def test_hauled_train_with_unknown_carriages(references):
    result = analyser_composition(_elements(*references))
    assert result["train_family"] == "Matériel tracté"
    assert result["train_type"] == "Locomotive BB 22200"
    assert result["train_units"] is None
    assert result["train_cars"] is None
    assert result["train_cars_source"] == "inconnue"
    assert result["train_composition"] == list(references)


def test_locomotive_with_known_trainset_is_not_classified_as_hauled():
    result = analyser_composition(_elements("0KSRABB22313", "Z24595"))
    assert result["train_family"] is None
    assert result["train_type"] is None


def test_unknown_carriage_reference_is_not_guessed():
    assert identifier_materiel("0KCBYLJH787U") is None
    assert identifier_materiel("ABCBB22313") is None


def test_duplicate_trainset_still_counted_once():
    result = analyser_composition(_elements("0KSRA-Z24727", "0KSRA-Z24727"))
    assert result["train_units"] == 1
    assert result["train_type"] == "TER 2N NG"