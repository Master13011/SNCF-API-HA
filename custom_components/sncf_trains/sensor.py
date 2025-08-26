from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN
from .coordinator import SncfUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    """Setup SNCF sensors from a config entry."""
    coordinator: SncfUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    departure = entry.data["from_id"]
    arrival = entry.data["to_id"]
    departure_name = entry.data.get("from_name", departure)
    arrival_name = entry.data.get("to_name", arrival)
    time_start = entry.options.get("time_start", "00:00")
    time_end = entry.options.get("time_end", "23:59")
    train_count = entry.options.get("train_count", 5)
    update_interval = entry.options.get("update_interval", 60)
    outside_interval = entry.options.get("outside_interval", 300)

    data: list[dict[str, Any]] = coordinator.data if isinstance(coordinator.data, list) else []
    direct_journeys: list[dict[str, Any]] = [
        j for j in data if isinstance(j, dict) and len(j.get("sections", [])) == 1
    ]

    # ✅ Cas : aucun trajet direct → sensor principal vide, pas d’enfants
    if not direct_journeys:
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
        main_sensor._journeys = []
        async_add_entities([main_sensor], True)
        return

    display_count = min(len(direct_journeys), train_count)

    entities: list[SensorEntity] = []

    # ✅ Capteur principal
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
    entities.append(main_sensor)

    # ✅ Nettoyage des anciens sensors enfants
    registry = er.async_get(hass)
    current_entities = {
        f"{DOMAIN}_{departure}_{arrival}_{i}" for i in range(1, display_count + 1)
    }
    for entity in list(registry.entities.values()):
        if (
            entity.platform == DOMAIN
            and entity.unique_id.startswith(f"{departure}_{arrival}_")
            and entity.unique_id not in current_entities
        ):
            _LOGGER.debug("Removing obsolete entity: %s", entity.entity_id)
            registry.async_remove(entity.entity_id)

    # ✅ Sensors enfants pour chaque train
    for i in range(display_count):
        train_sensor = SncfTrainSensor(
            coordinator,
            departure,
            arrival,
            departure_name,
            arrival_name,
            i + 1,
        )
        train_sensor._journeys = direct_journeys
        entities.append(train_sensor)

    async_add_entities(entities, True)


class SncfJourneySensor(CoordinatorEntity, SensorEntity):
    """Capteur principal SNCF avec résumé des trajets."""

    _attr_icon = "mdi:train"

    def __init__(
        self,
        coordinator: SncfUpdateCoordinator,
        departure: str,
        arrival: str,
        departure_name: str,
        arrival_name: str,
        time_start: str,
        time_end: str,
        update_interval: int,
        outside_interval: int,
    ) -> None:
        super().__init__(coordinator)
        self._departure = departure
        self._arrival = arrival
        self._departure_name = departure_name
        self._arrival_name = arrival_name
        self._journeys: list[dict[str, Any]] = []
        self._attr_name = f"SNCF {departure_name} → {arrival_name}"
        self._attr_unique_id = f"{departure}_{arrival}_main"
        self._time_start = time_start
        self._time_end = time_end
        self._update_interval = update_interval
        self._outside_interval = outside_interval

    @property
    def native_value(self) -> int:
        return len(self._journeys)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "departure": self._departure_name,
            "arrival": self._arrival_name,
            "time_window": f"{self._time_start}-{self._time_end}",
            "update_interval": self._update_interval,
            "outside_interval": self._outside_interval,
            "journeys": [self._format_journey(j) for j in self._journeys],
        }

    def _format_journey(self, journey: dict[str, Any]) -> dict[str, Any]:
        section = journey.get("sections", [{}])[0]
        display_info = section.get("display_informations", {})
        return {
            "departure_time": format_time(section.get("departure_date_time")),
            "arrival_time": format_time(section.get("arrival_date_time")),
            "duration_minutes": journey.get("duration", 0) // 60,
            "train_number": display_info.get("headsign"),
            "direction": display_info.get("direction"),
            "mode": display_info.get("commercial_mode"),
        }

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._departure}_{self._arrival}")},
            name=f"SNCF {self._departure_name} → {self._arrival_name}",
            manufacturer="SNCF",
            model="Train Journey",
        )


class SncfTrainSensor(CoordinatorEntity, SensorEntity):
    """Capteur enfant représentant un train spécifique."""

    _attr_icon = "mdi:train"

    def __init__(
        self,
        coordinator: SncfUpdateCoordinator,
        departure: str,
        arrival: str,
        departure_name: str,
        arrival_name: str,
        index: int,
    ) -> None:
        super().__init__(coordinator)
        self._departure = departure
        self._arrival = arrival
        self._departure_name = departure_name
        self._arrival_name = arrival_name
        self._index = index
        self._journeys: list[dict[str, Any]] = []
        self._attr_name = f"Train {index}: {departure_name} → {arrival_name}"
        self._attr_unique_id = f"{departure}_{arrival}_{index}"

    @property
    def native_value(self) -> str | None:
        if len(self._journeys) < self._index:
            return None
        section = self._journeys[self._index - 1].get("sections", [{}])[0]
        return format_time(section.get("departure_date_time"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if len(self._journeys) < self._index:
            return {}
        journey = self._journeys[self._index - 1]
        section = journey.get("sections", [{}])[0]
        display_info = section.get("display_informations", {})
        base = {
            "departure": self._departure_name,
            "arrival": self._arrival_name,
            "duration_minutes": journey.get("duration", 0) // 60,
            "train_number": display_info.get("headsign"),
            "direction": display_info.get("direction"),
            "mode": display_info.get("commercial_mode"),
        }
        return base


# ✅ Utils
def parse_datetime(dt_str: str | None) -> datetime | None:
    if not dt_str:
        return None
    try:
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None


def format_time(dt_str: str | None) -> str | None:
    dt = parse_datetime(dt_str)
    return dt.strftime("%H:%M") if dt else None
