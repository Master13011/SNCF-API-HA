import logging
import asyncio
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import CONF_API_KEY, CONF_FROM, CONF_TO, CONF_TIME_START, CONF_TIME_END

_LOGGER = logging.getLogger(__name__)
API_URL = "https://api.sncf.com/v1/coverage/sncf/journeys"

def parse_datetime(dt_str):
    if dt_str is None:
        return None
    try:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
    except Exception:
        return None

def format_time(dt_str):
    dt = parse_datetime(dt_str)
    return dt.strftime("%d/%m/%Y - %H:%M") if dt else None

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    api_key = entry.data[CONF_API_KEY]
    departure = entry.data[CONF_FROM]
    arrival = entry.data[CONF_TO]
    departure_name = entry.data.get("departure_name", departure)
    arrival_name = entry.data.get("arrival_name", arrival)
    time_start = entry.data.get(CONF_TIME_START, "07:00")
    time_end = entry.data.get(CONF_TIME_END, "10:00")

    options = entry.options
    update_interval = int(options.get("update_interval", 2))
    outside_interval = int(options.get("outside_interval", 60))

    sensor = SncfJourneySensor(
        hass, api_key, departure, arrival,
        departure_name, arrival_name,
        time_start, time_end,
        update_interval, outside_interval
    )

    async def async_update(now=None):
        await sensor.async_update()

    def get_interval():
        now = datetime.now()
        h_start, m_start = map(int, time_start.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        if now < dt_start - timedelta(hours=2):
            return timedelta(minutes=outside_interval)
        return timedelta(minutes=update_interval)

    async_track_time_interval(hass, async_update, get_interval())
    await sensor.async_update()
    async_add_entities([sensor], True)

class SncfJourneySensor(Entity):
    def __init__(self, hass, api_key, departure, arrival, dep_name, arr_name, start_time, end_time, update_interval, outside_interval):
        self.hass = hass
        self.api_key = api_key
        self.departure = departure
        self.arrival = arrival
        self.dep_name = dep_name
        self.arr_name = arr_name
        self.start_time = start_time
        self.end_time = end_time
        self.update_interval = update_interval
        self.outside_interval = outside_interval
        self._attr_name = f"SNCF: {self.dep_name} → {self.arr_name}"
        self._attr_icon = "mdi:train"
        self._attr_native_unit_of_measurement = "trajets"
        self._attr_unique_id = f"sncf_trains_{self.departure}_{self.arrival}"
        self._attr_extra_state_attributes = {
            "next_trains": [],
            "departure_station": self.departure,
            "arrival_station": self.arrival,
            "departure_name": self.dep_name,
            "arrival_name": self.arr_name,
            "delay_minutes": [],
            "has_delay": False,
            "next_delay_minutes": None,
            "trains_summary": [],
        }
        self._state = None
        self.session = async_get_clientsession(hass)

    def _build_datetime_param(self):
        now = datetime.now()
        h_start, m_start = map(int, self.start_time.split(":"))
        h_end, m_end = map(int, self.end_time.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        dt_end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)
        if now > dt_end:
            dt_start += timedelta(days=1)
        return dt_start.strftime("%Y%m%dT%H%M%S")

    async def async_update(self):
        params = {
            "from": self.departure,
            "to": self.arrival,
            "datetime": self._build_datetime_param(),
            "count": 10,
            "data_freshness": "realtime",
            "datetime_represents": "departure",
        }
        headers = {"Authorization": self.api_key}
        try:
            async with self.session.get(API_URL, params=params, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    _LOGGER.error(f"SNCF API returned with status {resp.status}")
                    self._clear_data()
                    return
                data = await resp.json()
                journeys = data.get("journeys", [])
                delays = []
                next_delay = None
                trains_summary = []
                next_trains = []

                for i, j in enumerate(journeys):
                    section = j.get("sections", [{}])[0]
                    base_dep = format_time(section.get("base_departure_date_time"))
                    base_arr = format_time(section.get("base_arrival_date_time"))
                    arr_time = parse_datetime(j.get("arrival_date_time"))
                    delay = int((arr_time - parse_datetime(section.get("base_arrival_date_time"))).total_seconds() / 60) if arr_time and section.get("base_arrival_date_time") else 0
                    delays.append(delay)
                    if i == 0:
                        next_delay = delay
                    next_trains.append(format_time(j.get("departure_date_time")))
                    trains_summary.append({
                        "departure_time": format_time(j.get("departure_date_time")),
                        "arrival_time": format_time(j.get("arrival_date_time")),
                        "base_departure_time": base_dep,
                        "base_arrival_time": base_arr,
                        "departure_stop_id": self.departure,
                        "arrival_stop_id": self.arrival,
                        "direction": section.get("display_informations", {}).get("direction", ""),
                        "physical_mode": section.get("display_informations", {}).get("physical_mode", ""),
                        "commercial_mode": section.get("display_informations", {}).get("commercial_mode", ""),
                        "delay_minutes": delay,
                        "has_delay": delay > 0
                    })

                self._attr_extra_state_attributes["next_trains"] = next_trains
                self._attr_extra_state_attributes["delay_minutes"] = delays
                self._attr_extra_state_attributes["has_delay"] = next_delay > 0
                self._attr_extra_state_attributes["next_delay_minutes"] = next_delay
                self._attr_extra_state_attributes["trains_summary"] = trains_summary
                self._state = len(journeys)
        except asyncio.TimeoutError:
            _LOGGER.error("Timeout fetching SNCF journeys data")
            self._clear_data()

    def _clear_data(self):
        self._attr_extra_state_attributes["next_trains"] = []
        self._attr_extra_state_attributes["delay_minutes"] = []
        self._attr_extra_state_attributes["has_delay"] = False
        self._attr_extra_state_attributes["next_delay_minutes"] = None
        self._attr_extra_state_attributes["trains_summary"] = []
        self._state = 0

    @property
    def state(self):
        return self._state
    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes

    @property
    def name(self):
        return self._attr_name

    @property
    def icon(self):
        return self._attr_icon

    @property
    def unique_id(self):
        return self._attr_unique_id
