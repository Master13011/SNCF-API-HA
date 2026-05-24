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

    # Capteur global "Trajets"
    async_add_entities([SncfJourneySensor(coordinator)], update_before_add=True)

    for subentry in entry.subentries.values():
        journeys = coordinator.data.get(subentry.subentry_id, [])
        display_count = min(len(journeys), subentry.data.get("train_count", 0))
        sensors = []

        # Capteurs individuels pour chaque train
        for idx in range(display_count):
            sensors.append(SncfTrainSensor(coordinator, subentry.subentry_id, idx))

        # Capteur résumé ligne par ligne
        sensors.append(SncfAllTrainsLineSensor(coordinator, subentry.subentry_id))

        # Ajouter tous les capteurs de cette subentry au même niveau
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
        self.journey = coordinator.data[train_id][journey_id]
        self.sections = self.journey.get("sections", [{}])[0]
        departure_time = parse_datetime(self.sections.get("base_departure_date_time", ""))

        self.departure = entry.data[CONF_FROM]
        self.arrival = entry.data[CONF_TO]

        self._attr_name = f"Train {journey_id + 1}"
        self._attr_unique_id = f"{entry.subentry_id}_{journey_id}"
        self._attr_extra_state_attributes = self._extra_attributes(self.journey)
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.subentry_id)},
            "name": f"SNCF {entry.data[CONF_DEPARTURE_NAME]} → {entry.data[CONF_ARRIVAL_NAME]}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }
        self._attr_native_value = departure_time
        # On appelle la fonction de mise à jour dès la création pour mutualiser le code
        self._update_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Appelé à chaque mise à jour de l'API."""
        self._update_state()
        self.async_write_ha_state()

    def _update_state(self) -> None:
        """Handle updated data from the coordinator."""
        self.journey = self.coordinator.data[self.tid][self.jid]
        if self.jid < len(self.journey):
            self.sections = self.journey.get("sections", [{}])[0]
            self._attr_native_value = parse_datetime(self.sections.get("base_departure_date_time", ""))
            self._attr_extra_state_attributes = self._extra_attributes(self.journey)
            self._attr_available = True  # Le capteur est actif
        else:
            # Si l'API est KO ou renvoie moins de trains que prévu
            self._attr_native_value = None
            self._attr_extra_state_attributes = {}
            self._attr_available = False # Le capteur passe en "Indisponible"

    def _extra_attributes(self, journey: dict[str, Any]) -> dict[str, Any]:
        """Extra attributes."""
        arr_dt = parse_datetime(self.sections.get("arrival_date_time", ""))
        base_arr_dt = parse_datetime(self.sections.get("base_arrival_date_time", ""))
        delay = (
            int((arr_dt - base_arr_dt).total_seconds() / 60)
            if arr_dt and base_arr_dt
            else 0
        )

        delay_cause = self._get_delay()

        route_details, stops_schedule = self._get_route()

        return {
            "departure_time": format_time(journey.get("departure_date_time", "")),
            "arrival_time": format_time(journey.get("arrival_date_time", "")),
            "base_departure_time": format_time(self.sections.get("base_departure_date_time")),
            "base_arrival_time": format_time(self.sections.get("base_arrival_date_time")),
            "delay_minutes": delay,
            "delay_cause": delay_cause,
            "duration_minutes": get_duration(journey),
            "has_delay": delay > 0,
            "route_details": route_details,
            "stops_schedule": stops_schedule,
            "departure_stop_id": self.departure,
            "arrival_stop_id": self.arrival,
            "direction": self.sections.get("display_informations", {}).get("direction", ""),
            "physical_mode": self.sections.get("display_informations", {}).get("physical_mode", ""),
            "commercial_mode": self.sections.get("display_informations", {}).get("commercial_mode", ""),
            "train_num": get_train_num(journey),
        }

    def _get_route(self) -> Any:
        impacted_stops = self.sections.get("impacted_stops", [])
        stops_list = []
        stops_schedule = []

        if impacted_stops:
            for stop in impacted_stops:
                stop_name = stop.get("stop_point", {}).get("name", "")
                b_raw = stop.get("base_departure_time") or stop.get("base_arrival_time")
                a_raw = stop.get("amended_departure_time") or stop.get("amended_arrival_time")

                b_time = f"{b_raw[:2]}:{b_raw[2:4]}" if b_raw and len(b_raw) >= 4 else ""
                a_time = f"{a_raw[:2]}:{a_raw[2:4]}" if a_raw and len(a_raw) >= 4 else ""

                stop_effect = stop.get("stop_time_effect", "unchanged")
                prefix = ""
                if stop_effect == "deleted":
                    prefix = "[SUPPRIMÉ] "
                elif stop_effect == "added":
                    prefix = "[NOUVEAU] "

                stops_list.append(f"{prefix}{stop_name} ({a_time if a_time else b_time})")
                stops_schedule.append({
                    "name": stop_name,
                    "base_time": b_time,
                    "amended_time": a_time if a_time != b_time else None,
                    "effect": stop_effect
                })
        else:
            stops_data = self.sections.get("stop_date_times", [])
            for stop in stops_data:
                stop_name = stop.get("stop_point", {}).get("name", "")
                raw_time = stop.get("departure_date_time", stop.get("arrival_date_time", ""))
                formatted_time = format_time(raw_time) if raw_time else ""
                stop_effect = stop.get("stop_time_effect", "unchanged")

                if stop_name and formatted_time:
                    prefix = ""
                    if stop_effect == "deleted":
                        prefix = "[SUPPRIMÉ] "
                    elif stop_effect == "added":
                        prefix = "[NOUVEAU] "

                    stops_list.append(f"{prefix}{stop_name} ({formatted_time})")
                    just_time = formatted_time.split(" - ")[-1] if " - " in formatted_time else formatted_time
                    stops_schedule.append({
                        "name": stop_name,
                        "time": just_time,
                        "base_time": just_time,
                        "amended_time": None,
                        "effect": stop_effect
                    })
        route_details = " ➔ ".join(stops_list)
        return route_details, stops_schedule

    def _get_delay(self) -> Any:
        delay_cause = self.sections.get("cause", "")

        if not delay_cause:
            messages = self.journey.get("messages", [])
            if messages:
                delay_cause = messages[0].get("text", "")

        if not delay_cause:
            disruptions = self.journey.get("_disruptions", [])
            links = self.sections.get("display_informations", {}).get("links", [])
            disruption_ids = [link.get("id") for link in links if link.get("type") == "disruption"]

            for disruption in disruptions:
                if disruption.get("id") in disruption_ids:
                    disruption_msgs = disruption.get("messages", [])
                    if disruption_msgs:
                        delay_cause = disruption_msgs[0].get("text", "")
                        break
        return delay_cause


class SncfAllTrainsLineSensor(CoordinatorEntity[SncfUpdateCoordinator], SensorEntity):
    """Sensor that aggregates all trains on a single line per attribute."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:train"
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: SncfUpdateCoordinator, train_id: str) -> None:
        """Initialize the line sensor."""
        super().__init__(coordinator)
        self.tid = train_id
        self._attr_name = "Tous les trains (ligne)"
        self._attr_unique_id = f"{train_id}_all_trains_line"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, train_id)},
            "name": "SNCF",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update all trains values on a single line."""
        journeys = self.coordinator.data.get(self.tid, [])
        departure_times = []
        base_departure_times = []
        delays = []
        overall_has_delay = False

        for journey in journeys:
            section = journey.get("sections", [{}])[0]
            arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
            base_arr_dt = parse_datetime(section.get("base_arrival_date_time"))
            delay = (
                int((arr_dt - base_arr_dt).total_seconds() / 60)
                if arr_dt and base_arr_dt
                else 0
            )

            departure_times.append(format_time(journey.get("departure_date_time", "")))
            base_departure_times.append(
                format_time(section.get("base_departure_date_time"))
            )
            delays.append(str(delay))

            if delay > 0:
                overall_has_delay = True

        self._attr_extra_state_attributes = {
            "departure_time": "; ".join(departure_times),
            "base_departure_time": "; ".join(base_departure_times),
            "delay_minutes": "; ".join(delays),
            "has_delay": overall_has_delay,
        }

        # On peut mettre un "native_value" arbitraire, par exemple le nombre de trains
        self._attr_native_value = len(journeys)

        self.async_write_ha_state()
