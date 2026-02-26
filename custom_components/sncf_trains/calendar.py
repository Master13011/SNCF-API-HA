import base64
import logging
from aiohttp import ClientSession, ClientTimeout
from typing import List, Optional, Mapping
from homeassistant.exceptions import ConfigEntryAuthFailed

API_BASE = "https://api.sncf.com"
_LOGGER = logging.getLogger(__name__)


def encode_token(api_key: str) -> str:
    """Encode the API key for Basic Auth."""
    token_str = f"{api_key}:"
    return base64.b64encode(token_str.encode()).decode()


class SncfApiClient:
    def __init__(self, session: ClientSession, api_key: str, timeout: int = 10):
        self._session = session
        self._token = encode_token(api_key)
        self._timeout = timeout

    async def fetch_departures(
        self, stop_id: str, max_results: int = 10
    ) -> Optional[List[dict]]:
        if stop_id.startswith("stop_area:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_areas/{stop_id}/departures"
        elif stop_id.startswith("stop_point:"):
            url = f"{API_BASE}/v1/coverage/sncf/stop_points/{stop_id}/departures"
        else:
            raise ValueError("stop_id must start with 'stop_area:' or 'stop_point:'")

        params_raw: dict[str, object] = {
            "data_freshness": "realtime",
            "count": max_results,
        }
        params: Mapping[str, str] = {k: str(v) for k, v in params_raw.items()}

        headers = {"Authorization": f"Basic {self._token}"}

        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 401:
                    # vrai problème d'auth
                    raise ConfigEntryAuthFailed("Unauthorized: check your API key.")
                if resp.status == 429:
                    # rate-limit => pas une auth failure
                    _LOGGER.warning("API rate limit (429) on %s with %s", url, params)
                    raise RuntimeError(
                        "SNCF API rate-limited (429)"
                    )  # sera géré comme non-critique
                resp.raise_for_status()
                data = await resp.json()
                return data.get("departures", [])
        except Exception as e:
            _LOGGER.error("Error fetching departures from SNCF API: %s", e)
            _LOGGER.debug("URL: %s, Params: %s", url, params)
            return None

    async def fetch_journeys(
        self, from_id: str, to_id: str, datetime_str: str, count: int = 5
    ) -> Optional[List[dict]]:
        url = f"{API_BASE}/v1/coverage/sncf/journeys"
        params_raw: dict[str, object] = {
            "from": from_id,
            "to": to_id,
            "datetime": datetime_str,
            "count": count,
            "data_freshness": "realtime",
            "datetime_represents": "departure",
        }
        params: Mapping[str, str] = {k: str(v) for k, v in params_raw.items()}

        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                if resp.status == 401:
                    raise ConfigEntryAuthFailed("Unauthorized: check your API key.")
                if resp.status == 429:
                    raise RuntimeError("Quota exceeded: 429 Too Many Requests.")
                resp.raise_for_status()
                data = await resp.json()
                return data.get("journeys", [])
        except Exception as e:
            _LOGGER.error("Error fetching journeys from SNCF API: %s", e)
            return None

    async def search_stations(self, query: str) -> Optional[List[dict]]:
        url = f"{API_BASE}/v1/coverage/sncf/places"
        params_raw: dict[str, object] = {
            "q": query,
            "type[]": "stop_point",
        }
        params: Mapping[str, str] = {k: str(v) for k, v in params_raw.items()}
        headers = {"Authorization": f"Basic {self._token}"}
        try:
            async with self._session.get(
                url,
                headers=headers,
                params=params,
                timeout=ClientTimeout(total=self._timeout),
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("places", [])
        except Exception as e:
            _LOGGER.error("Error searching stations from SNCF API: %s", e)
            return None
vdimaccio@vd-test-ubuntu22:~/git/SNCF-API-HA/custom_components/sncf_trains$ cat /home/vdimaccio/git/SNCF-API-HA/custom_components/sncf_trains/calendar.py
"""Calendar for trains hours."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SncfDataConfigEntry
from .const import CONF_ARRIVAL_NAME, CONF_DEPARTURE_NAME, CONF_TRAIN_COUNT, DOMAIN
from .coordinator import SncfUpdateCoordinator
from .helpers import get_train_num, parse_datetime

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SncfDataConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Demo Calendar config entry."""
    coordinator: SncfUpdateCoordinator = entry.runtime_data
    async_add_entities([SNCFCalendar(coordinator)], update_before_add=True)


@dataclass
class SNCFEventMixIn:
    """Mixin for calendar event."""

    has_delay: bool
    delay: int
    departure_date_time: datetime
    arrival_date_time: datetime
    train_num: int


@dataclass
class MyCalendarEvent(CalendarEvent, SNCFEventMixIn):
    """A class to describe a calendar event."""


class SNCFCalendar(CoordinatorEntity[SncfUpdateCoordinator], CalendarEntity):
    """Representation of a Calendar element."""

    _attr_name = "Trains"

    def __init__(self, coordinator: SncfUpdateCoordinator) -> None:
        """Initialize demo calendar."""
        super().__init__(coordinator)
        self._event: MyCalendarEvent | None = None
        self._attr_unique_id = f"calendar_sncf_train_{coordinator.entry.entry_id}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, coordinator.entry.entry_id)},
            "name": "SNCF",
            "manufacturer": "Master13011",
            "model": "API",
            "entry_type": DeviceEntryType.SERVICE,
        }

    @property
    def event(self) -> MyCalendarEvent | None:
        """Return the current or next upcoming event."""
        if not self.available:
            return None

        return self._event

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if self._fetch_journeys():
            self._event = min(
                self._fetch_journeys(),
                key=lambda x: abs(x.start.replace(tzinfo=None) - datetime.now()),
            )
            if self._event:
                self._attr_extra_state_attributes = {
                    "has_delay": self._event.has_delay,
                    "delay": self._event.delay,
                    "departure": self._event.departure_date_time,
                    "arrival": self._event.arrival_date_time,
                    "number": self._event.train_num,
                }
        self.async_write_ha_state()

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
        """Fetch journeys."""
        calendar_events = []
        for tid, journeys in self.coordinator.data.items():
            entry = self.coordinator.entry.subentries[tid]
            dep_name = entry.data[CONF_DEPARTURE_NAME]
            arr_name = entry.data[CONF_ARRIVAL_NAME]
            display_count = min(len(journeys), entry.data[CONF_TRAIN_COUNT])
            _LOGGER.debug("%s -> %s", dep_name, arr_name)
            for journey in journeys[:display_count]:
                section = journey.get("sections", [{}])[0]
                dep_dt = parse_datetime(journey.get("departure_date_time", ""))
                arr_dt = parse_datetime(journey.get("arrival_date_time", ""))
                has_delay, delay, summary = self._async_calculate_delay(
                    journey, dep_name, arr_name
                )

                if dep_dt and arr_dt:
                    calendar_events.append(
                        MyCalendarEvent(
                            summary=summary,
                            start=dep_dt,
                            end=dep_dt + timedelta(minutes=1),
                            description=f"Arrivée: {arr_dt}, retard: {delay} minutes",
                            location=str(dep_name),
                            uid=section.get("id"),
                            has_delay=has_delay,
                            delay=delay,
                            departure_date_time=dep_dt,
                            arrival_date_time=arr_dt,
                            train_num=int(get_train_num(journey)),
                        )
                    )

        return calendar_events