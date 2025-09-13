"""Calendar for trains hours."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SncfDataConfigEntry
from .const import DOMAIN
from .coordinator import SncfUpdateCoordinator
from .helpers import parse_datetime


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
        self.dep_name = coordinator.departure_name
        self.arr_name = coordinator.arrival_name

        self._attr_unique_id = f"calendar_sncf_train_{coordinator.entry.entry_id}"
        self._attr_name = "SNCF Train"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": f"SNCF {self.dep_name} → {self.arr_name}",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def event(self) -> CalendarEvent | None:
        """Return the current or next upcoming event."""
        if not self.available:
            return None

        journey = self.coordinator.data["journey_0"]
        has_delay, delay, _ = self._async_calculate_delay(journey)
        section = journey.get("sections", [{}])[0]
        dep_dt = parse_datetime(section.get("base_departure_date_time", ""))
        arr_dt = parse_datetime(section.get("base_arrival_date_time", ""))
        self._attr_extra_state_attributes = {"has_delay": has_delay, "delay": delay}
        if dep_dt and arr_dt:
            return CalendarEvent(
                summary=f"{self.dep_name} → {self.arr_name}", start=dep_dt, end=arr_dt
            )

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """Return calendar events within a datetime range.

        This is only called when opening the calendar in the UI.
        """
        if not self.available:
            return []

        calendar_events = []
        display_count = min(len(self.coordinator.data), self.coordinator.train_count)
        for journey in self.coordinator.data.values():
            if len(calendar_events) >= display_count:
                break
            section = journey.get("sections", [{}])[0]
            dep_dt = parse_datetime(journey.get("departure_date_time", ""))
            arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
            _, _, summary = self._async_calculate_delay(journey)

            if dep_dt and arr_dt:
                calendar_events.append(
                    CalendarEvent(
                        summary=summary,
                        start=dep_dt,
                        end=arr_dt,
                        location=section.get("from", {}).get("name"),
                        uid=section.get("id"),
                    )
                )
        return calendar_events

    def _async_calculate_delay(self, journey) -> tuple[bool, int, str]:
        arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
        section = journey.get("sections", [{}])[0]
        base_arr_dt = parse_datetime(section.get("base_arrival_date_time", ""))

        delay = (
            int((arr_dt - base_arr_dt).total_seconds() / 60)
            if arr_dt and base_arr_dt
            else 0
        )
        summary = (
            f"RETARD ({delay}) - {self.dep_name} → {self.arr_name}"
            if delay > 0
            else f"{self.dep_name} → {self.arr_name}"
        )

        return delay > 0, delay, summary
