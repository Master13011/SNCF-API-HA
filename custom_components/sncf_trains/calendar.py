"""Calendar for trains hours."""

import logging
from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt

from . import SncfDataConfigEntry
from .const import CONF_ARRIVAL_NAME, CONF_DEPARTURE_NAME, CONF_TRAIN_COUNT, DOMAIN
from .coordinator import SncfUpdateCoordinator
from .helpers import parse_datetime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SncfDataConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Demo Calendar config entry."""
    coordinator: SncfUpdateCoordinator = entry.runtime_data
    async_add_entities([SNCFCalendar(coordinator)])


class SNCFCalendar(CoordinatorEntity[SncfUpdateCoordinator], CalendarEntity):
    """Representation of a Calendar element."""

    _attr_name: str | None = None

    def __init__(self, coordinator: SncfUpdateCoordinator) -> None:
        """Initialize demo calendar."""
        super().__init__(coordinator)
        self._event: CalendarEvent | None = None
        self._attr_unique_id = f"calendar_sncf_train_{coordinator.entry.entry_id}"
        self._attr_name = "SNCF Train"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "SNCF Trains",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        if not self.available:
            return None

        return min(self._fetch_journeys(), key=lambda x: abs(x.start - dt.now()))

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range.

        This is only called when opening the calendar in the UI.
        """
        if not self.available:
            return []

        return self._fetch_journeys()

    def _async_calculate_delay(
        self, journey, dep_name: str, arr_name: str
    ) -> tuple[bool, int, str]:
        arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
        section = journey.get("sections", [{}])[0]
        base_arr_dt = parse_datetime(section.get("base_arrival_date_time", ""))

        delay = (
            int((arr_dt - base_arr_dt).total_seconds() / 60)
            if arr_dt and base_arr_dt
            else 0
        )
        summary = (
            f"{dep_name} → {arr_name} - RETARD ({delay}min)"
            if delay > 0
            else f"{dep_name} → {arr_name}"
        )

        return delay > 0, delay, summary

    def _fetch_journeys(self):
        """Fetch journeys"""
        calendar_events = []
        for tid, journeys in self.coordinator.data.items():
            entry = self.coordinator.entry.subentries[tid]
            dep_name = entry.data[CONF_DEPARTURE_NAME]
            arr_name = entry.data[CONF_ARRIVAL_NAME]
            display_count = min(len(journeys), entry.data[CONF_TRAIN_COUNT])
            _LOGGER.debug(f"{dep_name} -> {arr_name}")
            for journey in journeys[:display_count]:
                section = journey.get("sections", [{}])[0]
                dep_dt = parse_datetime(journey.get("departure_date_time", ""))
                arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
                _, _, summary = self._async_calculate_delay(journey, dep_name, arr_name)

                if dep_dt and arr_dt:
                    calendar_events.append(
                        CalendarEvent(
                            summary=summary,
                            start=dep_dt,
                            end=dep_dt,
                            description=f"Arrivée: {arr_dt}",
                            location=section.get("from", {}).get("name"),
                            uid=section.get("id"),
                        )
                    )

        return calendar_events
