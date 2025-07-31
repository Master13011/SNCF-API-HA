import logging
from datetime import datetime, timedelta
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.const import STATE_UNAVAILABLE

from .const import (
    CONF_API_KEY, CONF_FROM, CONF_TO,
    CONF_TIME_START, CONF_TIME_END,
    DEFAULT_UPDATE_INTERVAL, DEFAULT_OUTSIDE_INTERVAL,
)
from .api import SncfApiClient

_LOGGER = logging.getLogger(__name__)

def parse_datetime(dt_str):
    if dt_str is None:
        return None
    try:
        return datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
    except Exception:
        return None

def format_time(dt_str):
    dt = parse_datetime(dt_str)
    if not dt:
        return "N/A"  # Valeur de fallback pour éviter état None
    return dt.strftime("%d/%m/%Y - %H:%M")

async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities):
    api_key = entry.data[CONF_API_KEY]
    departure = entry.data[CONF_FROM]
    arrival = entry.data[CONF_TO]
    departure_name = entry.data.get("departure_name", departure)
    arrival_name = entry.data.get("arrival_name", arrival)
    time_start = entry.data.get(CONF_TIME_START, "07:00")
    time_end = entry.data.get(CONF_TIME_END, "10:00")
    update_interval = DEFAULT_UPDATE_INTERVAL
    outside_interval = DEFAULT_OUTSIDE_INTERVAL

    session = async_get_clientsession(hass)
    api_client = SncfApiClient(session, api_key)

    main_sensor = SncfJourneySensor(
        api_client, departure, arrival, departure_name, arrival_name,
        time_start, time_end, update_interval, outside_interval
    )
    train_sensors = [
        SncfTrainSensor(main_sensor, index) for index in range(3)
    ]

    unsub_handle = {"unsub": None}

    async def schedule_next_update(_=None):
        if unsub_handle["unsub"]:
            unsub_handle["unsub"]()
            unsub_handle["unsub"] = None
        interval = main_sensor.get_interval()
        unsub_handle["unsub"] = async_call_later(
            hass, interval.total_seconds(), async_update
        )

    async def async_update(_=None):
        await main_sensor.async_update()
        for sensor in train_sensors:
            sensor.async_update_from_main()
        await schedule_next_update()

    # 1) Ajouter les entités AVANT toute mise à jour
    async_add_entities([main_sensor] + train_sensors, True)

    # 2) Ensuite appeler la première mise à jour
    await main_sensor.async_update()
    for sensor in train_sensors:
        sensor.async_update_from_main()

    # 3) Démarrer la planification des updates dynamiques
    await schedule_next_update()

    async def on_unload(_=None):
        if unsub_handle["unsub"]:
            unsub_handle["unsub"]()
            unsub_handle["unsub"] = None
    entry.async_on_unload(on_unload)

class SncfJourneySensor(SensorEntity):
    def __init__(self, api_client, departure, arrival, dep_name, arr_name, start_time, end_time, update_interval, outside_interval):
        self.api_client = api_client
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
        self._attr_extra_state_attributes = {}
        self._state = None
        self._journeys = []

    @property
    def state(self):
        return self._state

    def get_interval(self):
        now = datetime.now()
        h_start, m_start = map(int, self.start_time.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        h_end, m_end = map(int, self.end_time.split(":"))
        if now < dt_start - timedelta(hours=2):
            return timedelta(minutes=self.outside_interval)
        return timedelta(minutes=self.update_interval)

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
        datetime_str = self._build_datetime_param()
        journeys = await self.api_client.fetch_journeys(
            self.departure, self.arrival, datetime_str, count=10
        )

        if journeys is None:
            self._clear_data()
            self._state = STATE_UNAVAILABLE
            if self.entity_id is not None:
                self.async_write_ha_state()
            return

        self._journeys = journeys
        delays = []
        next_delay = None
        trains_summary = []
        next_trains = []
        for i, j in enumerate(journeys):
            section = j.get("sections", [{}])[0]
            base_dep = format_time(section.get("base_departure_date_time"))
            base_arr = format_time(section.get("base_arrival_date_time"))
            arr_time = parse_datetime(j.get("arrival_date_time"))
            if arr_time and section.get("base_arrival_date_time"):
                delay = int((arr_time - parse_datetime(section.get("base_arrival_date_time"))).total_seconds() / 60)
            else:
                delay = 0
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
                "has_delay": delay > 0,
            })
        self._attr_extra_state_attributes = {
            "next_trains": next_trains,
            "delay_minutes": delays,
            "has_delay": next_delay > 0 if next_delay is not None else False,
            "next_delay_minutes": next_delay,
            "trains_summary": trains_summary,
        }
        self._state = len(journeys)
        if self.entity_id is not None:
            self.async_write_ha_state()

    def _clear_data(self):
        self._attr_extra_state_attributes = {
            "next_trains": [],
            "delay_minutes": [],
            "has_delay": False,
            "next_delay_minutes": None,
            "trains_summary": [],
        }
        self._state = 0
        self._journeys = []

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes


class SncfTrainSensor(SensorEntity):
    def __init__(self, main_sensor: SncfJourneySensor, train_index: int):
        self.main_sensor = main_sensor
        self.train_index = train_index
        self._attr_name = f"SNCF Train #{train_index + 1} ({main_sensor.dep_name} → {main_sensor.arr_name})"
        self._attr_icon = "mdi:train"
        self._attr_unique_id = f"sncf_train_{main_sensor.departure}_{main_sensor.arrival}_{train_index}"
        self._attr_extra_state_attributes = {}
        self._state = None

    @property
    def state(self):
        return self._state

    def async_update_from_main(self):
        journeys = self.main_sensor._journeys
        if not journeys or len(journeys) <= self.train_index:
            self._clear_data()
            if self.entity_id is not None:
                self.async_write_ha_state()
            return
        journey = journeys[self.train_index]
        section = journey.get("sections", [{}])[0]
        base_dep = format_time(section.get("base_departure_date_time"))
        base_arr = format_time(section.get("base_arrival_date_time"))
        dep_time = format_time(journey.get("departure_date_time")) or "N/A"
        arr_time = format_time(journey.get("arrival_date_time")) or "N/A"
        arr_dt = parse_datetime(journey.get("arrival_date_time"))
        base_arr_dt = parse_datetime(section.get("base_arrival_date_time"))
        delay = int((arr_dt - base_arr_dt).total_seconds() / 60) if arr_dt and base_arr_dt else 0
        self._state = dep_time
        self._attr_extra_state_attributes = {
            "departure_time": dep_time,
            "arrival_time": arr_time,
            "base_departure_time": base_dep,
            "base_arrival_time": base_arr,
            "delay_minutes": delay,
            "has_delay": delay > 0,
            "departure_stop_id": self.main_sensor.departure,
            "arrival_stop_id": self.main_sensor.arrival,
            "direction": section.get("display_informations", {}).get("direction", ""),
            "physical_mode": section.get("display_informations", {}).get("physical_mode", ""),
            "commercial_mode": section.get("display_informations", {}).get("commercial_mode", ""),
        }
        if self.entity_id is not None:
            self.async_write_ha_state()

    def _clear_data(self):
        self._attr_state = "N/A"
        self._attr_extra_state_attributes = {}
        if self.entity_id is not None:
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes
