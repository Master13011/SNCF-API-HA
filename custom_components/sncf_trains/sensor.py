import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from homeassistant.util import dt as dt_util
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import (
    DOMAIN,
    CONF_FROM,
    CONF_TO,
    CONF_TIME_START,
    CONF_TIME_END,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_TRAIN_COUNT,
    ATTRIBUTION,
    DEFAULT_TIME_START,
    DEFAULT_TIME_END,
)
from .coordinator import SncfUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

# --- Helpers ---

def parse_datetime(dt_str: Optional[str]) -> Optional[datetime]:
    if not dt_str:
        return None
    try:
        dt = dt_util.parse_datetime(dt_str)  # parse with timezone info if possible
        return dt_util.as_local(dt) if dt else None  # convert to local timezone
    except Exception:
        return None

def format_time(dt_str: Optional[str]) -> str:
    dt = parse_datetime(dt_str)
    return dt.strftime("%d/%m/%Y - %H:%M") if dt else "N/A"

def format_time(dt_str: Optional[str]) -> str:
    """Format a Navitia datetime string as dd/mm/YYYY - HH:MM."""
    dt = parse_datetime(dt_str)
    return dt.strftime("%d/%m/%Y - %H:%M") if dt else "N/A"
    
def get_train_num(journey: dict) -> str:
    """Extract the commercial train number."""
    trip_num = journey.get("trip_short_name")
    if trip_num:
        return trip_num
    sections = journey.get("sections", [])
    if sections:
        infos = sections[0].get("display_informations", {})
        return infos.get("trip_short_name") or infos.get("num", "")
    return ""

def get_duration(journey: dict) -> int:
    """Compute journey duration in minutes."""
    dep = parse_datetime(journey.get("departure_date_time"))
    arr = parse_datetime(journey.get("arrival_date_time"))
    if dep and arr:
        return int((arr - dep).total_seconds() / 60)
    return 0

# --- Entities setup ---

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback
) -> None:
    """Set up SNCF entities from a config entry."""

    coordinator: SncfUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    departure = entry.data.get(CONF_FROM)
    arrival = entry.data.get(CONF_TO)
    departure_name = entry.data.get("departure_name", departure)
    arrival_name = entry.data.get("arrival_name", arrival)

    time_start = entry.options.get(CONF_TIME_START, entry.data.get(CONF_TIME_START, DEFAULT_TIME_START))
    time_end = entry.options.get(CONF_TIME_END, entry.data.get(CONF_TIME_END, DEFAULT_TIME_END))
    update_interval = entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL)
    outside_interval = entry.options.get("outside_interval", DEFAULT_OUTSIDE_INTERVAL)
    train_count = entry.options.get("train_count", DEFAULT_TRAIN_COUNT)

    # Identifier unique pour cette entrée
    entry_suffix = entry.data.get("entry_suffix", entry.entry_id)

    data: List[Dict[str, Any]] = coordinator.data if isinstance(coordinator.data, list) else []

    # Filtrer les trajets directs uniquement (une seule section)
    direct_journeys = [j for j in data if isinstance(j, dict) and len(j.get("sections", [])) == 1]
    display_count = min(len(direct_journeys), train_count)

    sensors: List[SensorEntity] = []

    # Always create main sensor
    main_sensor = SncfJourneySensor(
        coordinator,
        departure, arrival,
        departure_name, arrival_name,
        time_start, time_end,
        update_interval, outside_interval,
        entry_suffix,
    )
    main_sensor._journeys = direct_journeys
    sensors.append(main_sensor)

    # Create child sensors
    for idx in range(display_count):
        train_sensor = SncfTrainSensor(main_sensor, idx, entry_suffix)
        sensors.append(train_sensor)
        main_sensor._child_sensors.append(train_sensor)

    # Remove obsolete child sensors
    entity_registry = async_get_entity_registry(hass)
    prefix = f"sncf_train_{departure}_{arrival}_{entry_suffix}_"

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

class SncfJourneySensor(CoordinatorEntity, SensorEntity):
    """Main SNCF sensor: number of direct journeys & summary."""

    def __init__(
        self, coordinator, departure, arrival, departure_name, arrival_name,
        start_time, end_time, update_interval, outside_interval, entry_suffix,
    ):
        super().__init__(coordinator)
        self.departure = departure
        self.arrival = arrival
        self.dep_name = departure_name
        self.arr_name = arrival_name
        self.start_time = start_time
        self.end_time = end_time
        self.update_interval = update_interval
        self.outside_interval = outside_interval
        self.entry_suffix = entry_suffix

        self._attr_name = f"SNCF: {self.dep_name} → {self.arr_name}"
        self._attr_icon = "mdi:train"
        self._attr_native_unit_of_measurement = "trajets"
        self._attr_unique_id = f"sncf_trains_{self.departure}_{self.arrival}_{entry_suffix}"
        self._attr_attribution = ATTRIBUTION

        self._journeys: List[dict] = []
        self._child_sensors: List[SensorEntity] = []

    @property
    def native_value(self) -> Optional[int]:
        journeys = self.coordinator.data or []
        direct_journeys = [j for j in journeys if len(j.get("sections", [])) == 1]
        self._journeys = direct_journeys
        return len(direct_journeys) if direct_journeys else None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        journeys = self._journeys
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

        for j in journeys:
            section = j.get("sections", [{}])[0]
            base_dep = format_time(section.get("base_departure_date_time"))
            base_arr = format_time(section.get("base_arrival_date_time"))
            arr_time = parse_datetime(j.get("arrival_date_time"))
            base_arrival = parse_datetime(section.get("base_arrival_date_time"))
            delay = int((arr_time - base_arrival).total_seconds() / 60) if arr_time and base_arrival else 0
            delays.append(delay)
            if delay > 0:
                overall_has_delay = True
            next_trains.append(format_time(j.get("departure_date_time")))
            summary.append({
                "departure_time": format_time(j.get("departure_date_time")),
                "arrival_time": format_time(j.get("arrival_date_time")),
                "base_departure_time": base_dep,
                "base_arrival_time": base_arr,
                "departure_stop_id": self.departure,
                "arrival_stop_id": self.arrival,
                "direction": section.get("display_informations", {}).get("direction", ""),
                "physical_mode": section.get("display_informations", {}).get("physical_mode", ""),
                "commercial_mode": section.get("display_informations", {}).get("commercial_mode", ""),
                "train_num": get_train_num(j),
                "delay_minutes": delay,
                "has_delay": delay > 0,
            })
    
        return {
            "next_trains": next_trains,
            "delay_minutes": delays,
            "has_delay": overall_has_delay,
            "trains_summary": summary,
            "time_window": f"{self.start_time} - {self.end_time}",
            "update_interval": self.update_interval,
            "outside_interval": self.outside_interval,
        }
        
    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        entry_id = getattr(self.coordinator.config_entry, "entry_id", None)
        if not entry_id:
            return None
        return {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"SNCF {self.dep_name} → {self.arr_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }

class SncfTrainSensor(CoordinatorEntity, SensorEntity):
    """Sensor for an individual train."""

    def __init__(self, main_sensor: SncfJourneySensor, train_index: int, entry_suffix: str):
        super().__init__(main_sensor.coordinator)
        self.main_sensor = main_sensor
        self.train_index = train_index
        self.entry_suffix = entry_suffix

        self._attr_name = f"SNCF Train #{train_index + 1} ({main_sensor.dep_name} → {main_sensor.arr_name})"
        self._attr_icon = "mdi:train"
        self._attr_unique_id = f"sncf_train_{main_sensor.departure}_{main_sensor.arrival}_{train_index}_{entry_suffix}"
        self._attr_attribution = ATTRIBUTION
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> Optional[datetime]:
        journeys = self.main_sensor._journeys
        if not journeys or len(journeys) <= self.train_index:
            return None
    
        section = journeys[self.train_index].get("sections", [{}])[0]
        return parse_datetime(section.get("base_departure_date_time"))

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        journeys = self.main_sensor._journeys
        if not journeys or len(journeys) <= self.train_index:
            return {}
        journey = journeys[self.train_index]
        section = journey.get("sections", [{}])[0]
        arr_dt = parse_datetime(journey.get("arrival_date_time"))
        base_arr_dt = parse_datetime(section.get("base_arrival_date_time"))
        delay = int((arr_dt - base_arr_dt).total_seconds() / 60) if arr_dt and base_arr_dt else 0
        return {
            "departure_time": format_time(journey.get("departure_date_time")),
            "arrival_time": format_time(journey.get("arrival_date_time")),
            "base_departure_time": format_time(section.get("base_departure_date_time")),
            "base_arrival_time": format_time(section.get("base_arrival_date_time")),
            "delay_minutes": delay,
            "duration_minutes": get_duration(journey),
            "has_delay": delay > 0,
            "departure_stop_id": self.main_sensor.departure,
            "arrival_stop_id": self.main_sensor.arrival,
            "direction": section.get("display_informations", {}).get("direction", ""),
            "physical_mode": section.get("display_informations", {}).get("physical_mode", ""),
            "commercial_mode": section.get("display_informations", {}).get("commercial_mode", ""),
            "train_num": get_train_num(journey),
        }

    @property
    def device_info(self) -> Optional[Dict[str, Any]]:
        entry_id = getattr(self.main_sensor.coordinator.config_entry, "entry_id", None)
        if not entry_id:
            return None
        return {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"SNCF {self.main_sensor.dep_name} → {self.main_sensor.arr_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }
