"""Sensors for trains hours."""

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SncfDataConfigEntry
from .const import (
    ATTRIBUTION,
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
    CONF_FROM,
    CONF_TO,
    DOMAIN,
)
from .coordinator import SncfUpdateCoordinator
from .helpers import format_time, get_duration, get_train_num, parse_datetime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SncfDataConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up SNCF entities from a config entry."""

    coordinator: SncfUpdateCoordinator = entry.runtime_data

    async_add_entities([SncfJourneySensor(coordinator)], update_before_add=True)

    for subentry in entry.subentries.values():
        journeys = coordinator.data[subentry.subentry_id]
        display_count = min(len(journeys), subentry.data["train_count"])
        sensors = []
        for idx in range(display_count):
            sensors.append(SncfTrainSensor(coordinator, subentry.subentry_id, idx))

        async_add_entities(
            sensors, config_subentry_id=subentry.subentry_id, update_before_add=True
        )


# --- Sensor Classes ---


class SncfJourneySensor(CoordinatorEntity[SncfUpdateCoordinator], SensorEntity):
    """Main SNCF sensor: number of direct journeys & summary."""

    _attr_has_entity_name = True
    _attr_name = "Trajets"
    _attr_icon = "mdi:train"
    _attr_native_unit_of_measurement = "trajets"

    def __init__(self, coordinator: SncfUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        self._attr_unique_id = f"sncf_trains_{coordinator.entry.entry_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "SNCF",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }
        self._attr_native_value = len(coordinator.data)
        self._attr_extra_state_attributes = {
            "update_interval": coordinator.update_interval_minutes,
            "outside_interval": coordinator.outside_interval_minutes,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._attr_native_value = len(self.coordinator.data)
        self._attr_extra_state_attributes = {
            "update_interval": self.coordinator.update_interval_minutes,
            "outside_interval": self.coordinator.outside_interval_minutes,
        }
        self.async_write_ha_state()


class SncfTrainSensor(CoordinatorEntity[SncfUpdateCoordinator], SensorEntity):
    """Sensor for an individual train."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:train"
    _attr_attribution = ATTRIBUTION
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, train_id: str, journey_id: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.tid = train_id
        self.jid = journey_id
        entry = self.coordinator.entry.subentries[train_id]
        journey = coordinator.data[train_id][journey_id]
        section = journey.get("sections", [{}])[0]
        departure_time = parse_datetime(section.get("base_departure_date_time", ""))
        dep_name = entry.data[CONF_DEPARTURE_NAME]
        arr_name = entry.data[CONF_ARRIVAL_NAME]

        self.departure = entry.data[CONF_FROM]
        self.arrival = entry.data[CONF_TO]

        self._attr_name = f"Train {journey_id + 1}"
        self._attr_unique_id = f"{entry.subentry_id}_{journey_id}"
        self._attr_extra_state_attributes = self._extra_attributes(journey)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.subentry_id)},
            "name": f"SNCF {dep_name} → {arr_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }
        self._attr_native_value = departure_time

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        journey = self.coordinator.data[self.tid][self.jid]
        section = journey.get("sections", [{}])[0]
        self._attr_native_value = parse_datetime(
            section.get("base_departure_date_time", "")
        )
        self._attr_extra_state_attributes = self._extra_attributes(journey)
        self.async_write_ha_state()

    def _extra_attributes(self, journey: dict[str, Any]) -> dict[str, Any]:
        """Extra attributes."""
        section = journey.get("sections", [{}])[0]
        arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
        base_arr_dt = parse_datetime(section.get("base_arrival_date_time"))
        delay = (
            int((arr_dt - base_arr_dt).total_seconds() / 60)
            if arr_dt and base_arr_dt
            else 0
        )
        return {
            "departure_time": format_time(journey.get("departure_date_time", "")),
            "arrival_time": format_time(journey.get("arrival_date_time", "")),
            "base_departure_time": format_time(section.get("base_departure_date_time")),
            "base_arrival_time": format_time(section.get("base_arrival_date_time")),
            "delay_minutes": delay,
            "duration_minutes": get_duration(journey),
            "has_delay": delay > 0,
            "departure_stop_id": self.departure,
            "arrival_stop_id": self.arrival,
            "direction": section.get("display_informations", {}).get("direction", ""),
            "physical_mode": section.get("display_informations", {}).get(
                "physical_mode", ""
            ),
            "commercial_mode": section.get("display_informations", {}).get(
                "commercial_mode", ""
            ),
            "train_num": get_train_num(journey),
        }
