"""Tests for the SNCF train sensors."""

from unittest.mock import MagicMock, patch

import pytest

from custom_components.sncf_trains.const import (
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
    CONF_FROM,
    CONF_TO,
    CONF_TRAIN_COUNT,
)
from custom_components.sncf_trains.sensor import (
    SncfAllTrainsLineSensor,
    SncfTrainSensor,
    async_setup_entry,
)


def _create_subentry(
    *,
    subentry_id: str = "subentry_1",
    train_count: int = 4,
) -> MagicMock:
    """Create a config subentry suitable for sensor tests."""
    subentry = MagicMock()
    subentry.subentry_id = subentry_id
    subentry.data = {
        CONF_FROM: "stop_area:dep",
        CONF_TO: "stop_area:arr",
        CONF_DEPARTURE_NAME: "Angerville",
        CONF_ARRIVAL_NAME: "Paris Austerlitz",
        CONF_TRAIN_COUNT: train_count,
    }
    return subentry


def _create_coordinator(
    *,
    subentries: dict,
    data: dict,
) -> MagicMock:
    """Create a coordinator mock suitable for sensor tests."""
    coordinator = MagicMock()
    coordinator.entry.entry_id = "entry_1"
    coordinator.entry.subentries = subentries
    coordinator.data = data
    coordinator.update_interval_minutes = 2
    coordinator.outside_interval_minutes = 60
    return coordinator


def _create_journey(base_departure: str = "20261109T070600") -> dict:
    """Create a minimal direct journey as returned by the SNCF API."""
    return {
        "departure_date_time": base_departure,
        "arrival_date_time": "20261109T080100",
        "sections": [
            {
                "type": "public_transport",
                "base_departure_date_time": base_departure,
                "base_arrival_date_time": "20261109T080100",
                "display_informations": {
                    "trip_short_name": "860582",
                },
            }
        ],
    }


@pytest.mark.asyncio
async def test_setup_creates_configured_number_of_train_sensors():
    """Test that all train sensors are created even with fewer journeys."""
    subentry = _create_subentry(train_count=4)

    coordinator = _create_coordinator(
        subentries={"subentry_1": subentry},
        data={"subentry_1": [_create_journey()]},
    )

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.subentries = {"subentry_1": subentry}

    added = []

    def _add_entities(entities, **kwargs):
        added.extend(entities)

    await async_setup_entry(MagicMock(), entry, _add_entities)

    train_sensors = [e for e in added if isinstance(e, SncfTrainSensor)]
    line_sensors = [e for e in added if isinstance(e, SncfAllTrainsLineSensor)]

    assert len(train_sensors) == 4
    assert len(line_sensors) == 1


@pytest.mark.asyncio
async def test_setup_without_any_journey():
    """Test that setup does not fail when the API returns no journey."""
    subentry = _create_subentry(train_count=2)

    coordinator = _create_coordinator(
        subentries={"subentry_1": subentry},
        data={},
    )

    entry = MagicMock()
    entry.runtime_data = coordinator
    entry.subentries = {"subentry_1": subentry}

    added = []

    def _add_entities(entities, **kwargs):
        added.extend(entities)

    await async_setup_entry(MagicMock(), entry, _add_entities)

    train_sensors = [e for e in added if isinstance(e, SncfTrainSensor)]

    assert len(train_sensors) == 2
    for sensor in train_sensors:
        assert sensor.native_value is None
        assert sensor.extra_state_attributes == {}


def test_train_sensor_is_filled_when_journey_appears():
    """Test that an empty train sensor is filled on the next update."""
    subentry = _create_subentry(train_count=2)

    coordinator = _create_coordinator(
        subentries={"subentry_1": subentry},
        data={"subentry_1": [_create_journey()]},
    )

    sensor = SncfTrainSensor(coordinator, "subentry_1", 1)

    assert sensor.native_value is None
    assert sensor.extra_state_attributes == {}

    coordinator.data = {
        "subentry_1": [
            _create_journey(),
            _create_journey("20261109T082300"),
        ]
    }

    with patch.object(sensor, "async_write_ha_state"):
        sensor._handle_coordinator_update()

    assert sensor.native_value is not None
    assert sensor.native_value.strftime("%H:%M") == "08:23"
    assert sensor.extra_state_attributes["base_departure_time"].endswith("08:23")
