import logging
from datetime import datetime
from homeassistant.util import dt as dt_util
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from typing import Any, cast

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


def parse_datetime(dt_str: str | None) -> datetime | None:
    """Convertit une string Navitia en datetime local Home Assistant."""
    if not dt_str:
        return None
    try:
        naive = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
        return dt_util.as_local(naive)
    except Exception:
        return None


def format_time(dt_str: str | None) -> str:
    """Formate une datetime Navitia en chaîne lisible (dd/mm/YYYY - HH:MM)."""
    dt = parse_datetime(dt_str)
    return dt.strftime("%d/%m/%Y - %H:%M") if dt else "N/A"


def get_train_num(journey: dict) -> str:
    """Extrait le numéro commercial du train."""
    trip_num = journey.get("trip_short_name")
    if trip_num:
        return trip_num
    sections = journey.get("sections", [])
    if sections:
        infos = sections[0].get("display_informations", {})
        return infos.get("trip_short_name") or infos.get("num", "")
    return ""


def get_duration(journey: dict) -> int:
    """Calcule la durée du trajet en minutes."""
    dep = parse_datetime(journey.get("departure_date_time"))
    arr = parse_datetime(journey.get("arrival_date_time"))
    return int((arr - dep).total_seconds() / 60) if dep and arr else 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Setup des capteurs pour l'entrée."""
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

    data: list[dict[str, Any]] = coordinator.data if isinstance(coordinator.data, list) else []
    direct_journeys: list[dict[str, Any]] = [j for j in data if isinstance(j, dict) and len(j.get("sections", [])) == 1]

    # Création du capteur principal
    main_sensor = SncfJourneySensor(
        coordinator,
        departure,
        arrival,
        departure_name,
        arrival_name,
        time_start,
        time_end,
        update_interval,
        outside_interval,
    )
    main_sensor._journeys = direct_journeys

    entities: list[SensorEntity] = [main_sensor]

    if direct_journeys:
        display_count = min(len(direct_journeys), train_count)
        train_sensors = [SncfTrainSensor(main_sensor, idx) for idx in range(display_count)]

        # Nettoyage des vieux capteurs obsolètes
        entity_registry = er.async_get(hass)
        prefix = f"sncf_train_{departure}_{arrival}_"
        for entity in list(entity_registry.entities.values()):
            if entity.domain == "sensor" and entity.unique_id.startswith(prefix):
                try:
                    index = int(entity.unique_id.split("_")[-1])
                    if index >= display_count:
                        _LOGGER.info("Suppression capteur obsolète : %s", entity.entity_id)
                        entity_registry.async_remove(entity.entity_id)
                except ValueError:
                    continue

        main_sensor._child_sensors.extend(train_sensors)
        entities.extend(train_sensors)

    async_add_entities(cast(list[SensorEntity], entities), True)


class SncfJourneySensor(CoordinatorEntity, SensorEntity):
    """Capteur principal résumant le nombre total de trajets directs."""

    def __init__(self, coordinator, departure, arrival, departure_name, arrival_name, start_time, end_time, update_interval, outside_interval):
        super().__init__(coordinator)
        self.departure = departure
        self.arrival = arrival
        self.dep_name = departure_name
        self.arr_name = arrival_name
        entry_id = coordinator.config_entry.entry_id
        self._attr_name = f"SNCF: {self.dep_name} → {self.arr_name}"
        self._attr_icon = "mdi:train"
        self._attr_native_unit_of_measurement = "trajets"
        self._attr_unique_id = f"{entry_id}_sncf_trains_{self.departure}_{self.arrival}"
        self._attr_attribution = ATTRIBUTION
        self._journeys: list[dict] = []
        self._child_sensors: list[SensorEntity] = []

    @property
    def native_value(self):
        journeys = self.coordinator.data or []
        direct_journeys = [j for j in journeys if len(j.get("sections", [])) == 1]
        self._journeys = direct_journeys
        return len(direct_journeys) if direct_journeys else None

    @property
    def extra_state_attributes(self):
        if not self._journeys:
            return {
                "next_trains": [],
                "delay_minutes": [],
                "has_delay": False,
                "next_delay_minutes": None,
                "trains_summary": [],
            }

        delays, trains_summary, next_trains = [], [], []
        next_delay = None

        for i, j in enumerate(self._journeys):
            section = j.get("sections", [{}])[0]
            arr_time = parse_datetime(j.get("arrival_date_time"))
            base_arrival = parse_datetime(section.get("base_arrival_date_time"))

            delay = int((arr_time - base_arrival).total_seconds() / 60) if arr_time and base_arrival else 0
            delays.append(delay)
            if i == 0:
                next_delay = delay

            next_trains.append(format_time(j.get("departure_date_time")))
            trains_summary.append({
                "departure_time": format_time(j.get("departure_date_time")),
                "arrival_time": format_time(j.get("arrival_date_time")),
                "base_departure_time": format_time(section.get("base_departure_date_time")),
                "base_arrival_time": format_time(section.get("base_arrival_date_time")),
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
            "next_trains": "• " + "  •  ".join(next_trains),
            "delay_minutes": delays,
            "has_delay": next_delay > 0 if next_delay is not None else False,
            "next_delay_minutes": next_delay,
            "trains_summary": trains_summary,
        }

    @property
    def device_info(self):
        entry_id = getattr(self.coordinator.config_entry, "entry_id", None)
        return {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"SNCF {self.dep_name} → {self.arr_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE
        } if entry_id else None


class SncfTrainSensor(CoordinatorEntity, SensorEntity):
    """Capteur représentant un train individuel avec ses attributs."""

    def __init__(self, main_sensor: SncfJourneySensor, train_index: int):
        super().__init__(main_sensor.coordinator)
        self.main_sensor = main_sensor
        self.train_index = train_index
        entry_id = main_sensor.coordinator.config_entry.entry_id
        self._attr_name = f"SNCF Train #{train_index + 1} ({main_sensor.dep_name} → {main_sensor.arr_name})"
        self._attr_icon = "mdi:train"
        self._attr_unique_id = f"{entry_id}_sncf_train_{main_sensor.departure}_{main_sensor.arrival}_{train_index}"
        self._attr_attribution = ATTRIBUTION
        self._attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self):
        journeys = self.main_sensor._journeys
        if not journeys or len(journeys) <= self.train_index:
            return None
        return parse_datetime(journeys[self.train_index].get("departure_date_time"))

    @property
    def extra_state_attributes(self):
        journeys = self.main_sensor._journeys
        if not journeys or len(journeys) <= self.train_index:
            return {}
        j = journeys[self.train_index]
        section = j.get("sections", [{}])[0]
        arr_dt = parse_datetime(j.get("arrival_date_time"))
        base_arr_dt = parse_datetime(section.get("base_arrival_date_time"))
        delay = int((arr_dt - base_arr_dt).total_seconds() / 60) if arr_dt and base_arr_dt else 0

        return {
            "departure_time": format_time(j.get("departure_date_time")),
            "arrival_time": format_time(j.get("arrival_date_time")),
            "base_departure_time": format_time(section.get("base_departure_date_time")),
            "base_arrival_time": format_time(section.get("base_arrival_date_time")),
            "delay_minutes": delay,
            "duration_minutes": get_duration(j),
            "has_delay": delay > 0,
            "departure_stop_id": self.main_sensor.departure,
            "arrival_stop_id": self.main_sensor.arrival,
            "direction": section.get("display_informations", {}).get("direction", ""),
            "physical_mode": section.get("display_informations", {}).get("physical_mode", ""),
            "commercial_mode": section.get("display_informations", {}).get("commercial_mode", ""),
            "train_num": get_train_num(j),
        }

    @property
    def device_info(self):
        entry_id = getattr(self.main_sensor.coordinator.config_entry, "entry_id", None)
        return {
            "identifiers": {(DOMAIN, entry_id)},
            "name": f"SNCF {self.main_sensor.dep_name} → {self.main_sensor.arr_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        } if entry_id else None
