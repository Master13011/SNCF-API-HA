"""Tests for the state and attributes of the SNCF sensors."""

from unittest.mock import MagicMock, patch

from custom_components.sncf_trains.const import (
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
    CONF_FROM,
    CONF_TO,
    CONF_TRAIN_COUNT,
)
from custom_components.sncf_trains.helpers import parse_datetime
from custom_components.sncf_trains.sensor import (
    SncfAllTrainsLineSensor,
    SncfJourneySensor,
    SncfTrainSensor,
    get_transport_section,
)


def _coordinator(data: dict) -> MagicMock:
    subentry = MagicMock()
    subentry.subentry_id = "sub1"
    subentry.data = {
        CONF_FROM: "stop_area:dep",
        CONF_TO: "stop_area:arr",
        CONF_DEPARTURE_NAME: "Angerville",
        CONF_ARRIVAL_NAME: "Paris Austerlitz",
        CONF_TRAIN_COUNT: 3,
    }
    coordinator = MagicMock()
    coordinator.entry.entry_id = "entry_1"
    coordinator.entry.subentries = {"sub1": subentry}
    coordinator.data = data
    coordinator.update_interval_minutes = 2
    coordinator.outside_interval_minutes = 60
    return coordinator


def _journey(
    *,
    dep: str = "20261109T070600",
    base_dep: str = "20261109T070600",
    arr: str = "20261109T080100",
    base_arr: str = "20261109T080100",
    **extra,
) -> dict:
    return {
        "departure_date_time": dep,
        "arrival_date_time": arr,
        "sections": [
            {
                "type": "public_transport",
                "base_departure_date_time": base_dep,
                "base_arrival_date_time": base_arr,
                "display_informations": {
                    "trip_short_name": "860582",
                    "direction": "Paris Austerlitz",
                    "physical_mode": "Train",
                    "commercial_mode": "TER",
                },
            }
        ],
        **extra,
    }


# --- get_transport_section ---------------------------------------------------


def test_transport_section_is_found_among_walking_sections():
    transport = {"type": "public_transport"}
    journey = {"sections": [{"type": "crow_fly"}, transport, {"type": "crow_fly"}]}
    assert get_transport_section(journey) is transport


def test_transport_section_falls_back_to_first_section():
    first = {"type": "street_network"}
    assert get_transport_section({"sections": ["oops", first]}) is first


def test_transport_section_of_malformed_journey_is_empty():
    assert get_transport_section({}) == {}
    assert get_transport_section({"sections": []}) == {}
    assert get_transport_section({"sections": "oops"}) == {}


# --- SncfJourneySensor -------------------------------------------------------


def test_journey_sensor_counts_configured_journeys():
    coordinator = _coordinator({"sub1": [_journey()], "sub2": []})

    sensor = SncfJourneySensor(coordinator)

    assert sensor.unique_id == "sncf_trains_entry_1"
    assert sensor.native_value == 2
    assert sensor.extra_state_attributes == {
        "update_interval": 2,
        "outside_interval": 60,
    }
    assert ("sncf_trains", "entry_1") in sensor.device_info["identifiers"]


def test_journey_sensor_follows_the_coordinator():
    coordinator = _coordinator({"sub1": [_journey()]})
    sensor = SncfJourneySensor(coordinator)

    coordinator.data = {}
    coordinator.update_interval_minutes = 5
    with patch.object(sensor, "async_write_ha_state") as write:
        sensor._handle_coordinator_update()

    write.assert_called_once()
    assert sensor.native_value == 0
    assert sensor.extra_state_attributes["update_interval"] == 5


# --- SncfTrainSensor ---------------------------------------------------------


def test_train_sensor_identity():
    sensor = SncfTrainSensor(_coordinator({"sub1": [_journey()]}), "sub1", 1)

    assert sensor.name == "Train 2"
    assert sensor.unique_id == "sub1_1"
    assert sensor.device_info["name"] == "SNCF Angerville → Paris Austerlitz"
    assert ("sncf_trains", "sub1") in sensor.device_info["identifiers"]


def test_train_sensor_state_is_the_scheduled_departure():
    sensor = SncfTrainSensor(
        _coordinator({"sub1": [_journey(base_dep="20261109T070100")]}), "sub1", 0
    )
    assert sensor.native_value == parse_datetime("20261109T070100")


def test_on_time_train_attributes():
    sensor = SncfTrainSensor(_coordinator({"sub1": [_journey()]}), "sub1", 0)

    attrs = sensor.extra_state_attributes

    assert attrs["departure_time"] == "09/11/2026 - 07:06"
    assert attrs["arrival_time"] == "09/11/2026 - 08:01"
    assert attrs["base_departure_time"] == "09/11/2026 - 07:06"
    assert attrs["base_arrival_time"] == "09/11/2026 - 08:01"
    assert attrs["delay_minutes"] == 0
    assert attrs["has_delay"] is False
    assert attrs["duration_minutes"] == 55
    assert attrs["departure_stop_id"] == "stop_area:dep"
    assert attrs["arrival_stop_id"] == "stop_area:arr"
    assert attrs["direction"] == "Paris Austerlitz"
    assert attrs["physical_mode"] == "Train"
    assert attrs["commercial_mode"] == "TER"
    assert attrs["train_num"] == "860582"
    assert attrs["journey_status"] is None


def test_delayed_train_attributes():
    journey = _journey(
        dep="20261109T071100",
        base_dep="20261109T070600",
        arr="20261109T081100",
        base_arr="20261109T080100",
        status="SIGNIFICANT_DELAYS",
    )
    sensor = SncfTrainSensor(_coordinator({"sub1": [journey]}), "sub1", 0)

    attrs = sensor.extra_state_attributes

    assert attrs["delay_minutes"] == 10
    assert attrs["has_delay"] is True
    assert attrs["departure_time"] == "09/11/2026 - 07:11"
    assert attrs["base_departure_time"] == "09/11/2026 - 07:06"
    assert attrs["journey_status"] == "SIGNIFICANT_DELAYS"


def test_unknown_enrichment_data_is_not_available():
    attrs = SncfTrainSensor(
        _coordinator({"sub1": [_journey()]}), "sub1", 0
    ).extra_state_attributes

    for key in (
        "platform",
        "arrival_platform",
        "train_units",
        "train_composition",
        "train_length",
        "train_family",
        "train_type",
        "train_cars",
        "train_cars_source",
    ):
        assert attrs[key] == "N/A", key


def test_enrichment_data_is_exposed():
    journey = _journey(
        platform_track="B",
        arrival_platform_track="12",
        train_units=1,
        train_composition=["0SSCA-B85075"],
        train_length=150,
        train_family="Régiolis",
        train_type="Coradia Liner",
        train_cars=6,
        train_cars_source="catalogue",
    )

    attrs = SncfTrainSensor(
        _coordinator({"sub1": [journey]}), "sub1", 0
    ).extra_state_attributes

    assert attrs["platform"] == "B"
    assert attrs["arrival_platform"] == "12"
    assert attrs["train_units"] == 1
    assert attrs["train_composition"] == ["0SSCA-B85075"]
    assert attrs["train_length"] == 150
    assert attrs["train_family"] == "Régiolis"
    assert attrs["train_type"] == "Coradia Liner"
    assert attrs["train_cars"] == 6
    assert attrs["train_cars_source"] == "catalogue"


def test_disruption_is_summarised_in_the_attributes():
    journey = _journey(
        disruptions=[
            {
                "cause": "Panne de signalisation",
                "severity": {"effect": "SIGNIFICANT_DELAYS"},
                "messages": [{"text": "Retard important"}],
            }
        ]
    )

    attrs = SncfTrainSensor(
        _coordinator({"sub1": [journey]}), "sub1", 0
    ).extra_state_attributes

    assert attrs["disruption_cause"] == "Panne de signalisation"
    assert attrs["disruption_effect"] == "SIGNIFICANT_DELAYS"
    assert attrs["disruption_message"] == "Retard important"


def test_train_sensor_is_emptied_when_the_journey_disappears():
    coordinator = _coordinator({"sub1": [_journey()]})
    sensor = SncfTrainSensor(coordinator, "sub1", 0)
    assert sensor.native_value is not None

    coordinator.data = {"sub1": []}
    with patch.object(sensor, "async_write_ha_state"):
        sensor._handle_coordinator_update()

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


def test_train_sensor_handles_missing_subentry_data():
    sensor = SncfTrainSensor(_coordinator({}), "sub1", 0)
    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}


# --- SncfAllTrainsLineSensor -------------------------------------------------


def test_line_sensor_identity():
    sensor = SncfAllTrainsLineSensor(_coordinator({}), "sub1")

    assert sensor.name == "Tous les trains (ligne)"
    assert sensor.unique_id == "sub1_all_trains_line"
    assert sensor.device_info["name"] == "SNCF Angerville → Paris Austerlitz"
    # Same device as the individual train sensors
    assert ("sncf_trains", "sub1") in sensor.device_info["identifiers"]


def test_line_sensor_aggregates_all_journeys():
    on_time = _journey()
    delayed = _journey(
        dep="20261109T082900",
        base_dep="20261109T082300",
        arr="20261109T091400",
        base_arr="20261109T090900",
    )

    sensor = SncfAllTrainsLineSensor(
        _coordinator({"sub1": [on_time, delayed]}), "sub1"
    )

    assert sensor.native_value == 2
    attrs = sensor.extra_state_attributes
    assert attrs["departure_time"] == "09/11/2026 - 07:06; 09/11/2026 - 08:29"
    assert attrs["base_departure_time"] == "09/11/2026 - 07:06; 09/11/2026 - 08:23"
    assert attrs["delay_minutes"] == "0; 5"
    assert attrs["has_delay"] is True


def test_line_sensor_without_delay():
    sensor = SncfAllTrainsLineSensor(_coordinator({"sub1": [_journey()]}), "sub1")
    assert sensor.extra_state_attributes["has_delay"] is False
    assert sensor.extra_state_attributes["delay_minutes"] == "0"


def test_line_sensor_without_journey():
    sensor = SncfAllTrainsLineSensor(_coordinator({"sub1": []}), "sub1")

    assert sensor.native_value == 0
    assert sensor.extra_state_attributes == {
        "departure_time": "",
        "base_departure_time": "",
        "delay_minutes": "",
        "has_delay": False,
    }


def test_line_sensor_ignores_malformed_journeys():
    sensor = SncfAllTrainsLineSensor(
        _coordinator({"sub1": ["oops", _journey()]}), "sub1"
    )
    assert sensor.extra_state_attributes["departure_time"] == "09/11/2026 - 07:06"


def test_line_sensor_follows_the_coordinator():
    coordinator = _coordinator({"sub1": []})
    sensor = SncfAllTrainsLineSensor(coordinator, "sub1")

    coordinator.data = {"sub1": [_journey()]}
    with patch.object(sensor, "async_write_ha_state") as write:
        sensor._handle_coordinator_update()

    write.assert_called_once()
    assert sensor.native_value == 1
