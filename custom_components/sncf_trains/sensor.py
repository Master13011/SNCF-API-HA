import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import SncfUpdateCoordinator
from .helpers import format_time, get_duration, get_train_num, parse_datetime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SNCF entities from a config entry."""

    coordinator: SncfUpdateCoordinator = entry.runtime_data

    sensors: list[SncfJourneySensor | SncfTrainSensor] = [
        SncfJourneySensor(coordinator)
    ]

    # Filtrer les trajets directs uniquement (une seule section)
    display_count = min(len(coordinator.data), coordinator.train_count)

    # Create child sensors
    for idx in range(display_count):
        sensors.append(SncfTrainSensor(coordinator, idx))

    # Remove obsolete child sensors
    entity_registry = async_get_entity_registry(hass)
    prefix = (
        f"sncf_train_{coordinator.departure}_{coordinator.arrival}_{entry.entry_id}_"
    )

    for entity in list(entity_registry.entities.values()):
        if entity.domain == "sensor" and entity.unique_id.startswith(prefix):
            try:
                idx = int(entity.unique_id.split("_")[-2])
            except (ValueError, IndexError):
                continue
            if idx >= display_count:
                _LOGGER.info("Removing obsolete train sensor: %s", entity.entity_id)
                entity_registry.async_remove(entity.entity_id)

    async_add_entities(sensors, True)


# --- Sensor Classes ---


class SncfJourneySensor(CoordinatorEntity[SncfUpdateCoordinator], SensorEntity):
    """Main SNCF sensor: number of direct journeys & summary."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: SncfUpdateCoordinator) -> None:
        """Initialize."""
        super().__init__(coordinator)
        journeys = coordinator.data
        self.departure = coordinator.departure
        self.arrival = coordinator.arrival
        self.dep_name = coordinator.departure_name
        self.arr_name = coordinator.arrival_name
        self.start_time = coordinator.time_start
        self.end_time = coordinator.time_end
        self.update_interval = coordinator.update_interval_minutes
        self.outside_interval = coordinator.outside_interval_minutes

        self._attr_name = f"SNCF: {self.dep_name} → {self.arr_name}"
        self._attr_icon = "mdi:train"
        self._attr_native_unit_of_measurement = "trajets"
        self._attr_unique_id = (
            f"sncf_trains_{self.departure}_{self.arrival}_{coordinator.entry.entry_id}"
        )
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"SNCF {coordinator.departure_name} → {coordinator.arrival_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }
        self._attr_native_value = len(journeys)
        self._attr_extra_state_attributes = self._extra_attributes(journeys)
        self._attr_attribution = ATTRIBUTION

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        journeys = self.coordinator.data
        self._attr_native_value = len(journeys)
        self._attr_extra_state_attributes = self._extra_attributes(journeys)
        self.async_write_ha_state()

    def _extra_attributes(self, journeys: dict[str, Any]) -> dict[str, Any]:
        """Extra attributes."""
        if not journeys:
            return {
                "next_trains": [],
                "delay_minutes": [],
                "has_delay": False,
                "trains_summary": [],
            }
        summary = []
        next_trains = []
        delays = []
        overall_has_delay = False

        for j in journeys.values():
            section = j.get("sections", [{}])[0]
            base_dep = format_time(section.get("base_departure_date_time"))
            base_arr = format_time(section.get("base_arrival_date_time"))
            arr_time = parse_datetime(j.get("arrival_date_time", ""))
            base_arrival = parse_datetime(section.get("base_arrival_date_time"))
            delay = (
                int((arr_time - base_arrival).total_seconds() / 60)
                if arr_time and base_arrival
                else 0
            )
            delays.append(delay)
            if delay > 0:
                overall_has_delay = True
            next_trains.append(format_time(j.get("departure_date_time", "")))
            summary.append(
                {
                    "departure_time": format_time(j.get("departure_date_time", "")),
                    "arrival_time": format_time(j.get("arrival_date_time", "")),
                    "base_departure_time": base_dep,
                    "base_arrival_time": base_arr,
                    "departure_stop_id": self.departure,
                    "arrival_stop_id": self.arrival,
                    "direction": section.get("display_informations", {}).get(
                        "direction", ""
                    ),
                    "physical_mode": section.get("display_informations", {}).get(
                        "physical_mode", ""
                    ),
                    "commercial_mode": section.get("display_informations", {}).get(
                        "commercial_mode", ""
                    ),
                    "train_num": get_train_num(j),
                    "delay_minutes": delay,
                    "has_delay": delay > 0,
                }
            )

        return {
            "next_trains": next_trains,
            "delay_minutes": delays,
            "has_delay": overall_has_delay,
            "trains_summary": summary,
            "time_window": f"{self.start_time} - {self.end_time}",
            "update_interval": self.update_interval,
            "outside_interval": self.outside_interval,
        }


class SncfTrainSensor(CoordinatorEntity[SncfUpdateCoordinator], SensorEntity):
    """Sensor for an individual train."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, train_index: int) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        journeys = coordinator.data
        self.train_index = train_index
        self.departure = coordinator.departure
        self.arrival = coordinator.arrival

        self._attr_name = f"SNCF Train #{train_index + 1} ({coordinator.departure_name} → {coordinator.arrival_name})"
        self._attr_icon = "mdi:train"
        self._attr_unique_id = f"sncf_train_{coordinator.departure}_{coordinator.arrival}_{train_index}_{coordinator.entry.entry_id}"
        self._attr_attribution = ATTRIBUTION
        self._attr_device_class = SensorDeviceClass.TIMESTAMP
        self._attr_extra_state_attributes = self._extra_attributes(journeys)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"SNCF {coordinator.departure_name} → {coordinator.arrival_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }

        section = journeys.get(f"journey_{train_index}", {}).get("sections", [{}])[0]
        self._attr_native_value = parse_datetime(
            section.get("base_departure_date_time", "")
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        journeys = self.coordinator.data
        journey = journeys.get(f"journey_{self.train_index}", {})
        section = journey.get("sections", [{}])[0]
        self._attr_native_value = parse_datetime(
            section.get("base_departure_date_time", "")
        )
        self._attr_extra_state_attributes = self._extra_attributes(journeys)
        self.async_write_ha_state()

    def _extra_attributes(self, journeys: dict[str, Any]) -> dict[str, Any]:
        """Extra attributes."""
        journey = journeys.get(f"journey_{self.train_index}", {})
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
