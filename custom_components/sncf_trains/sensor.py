import logging
from datetime import datetime, timedelta
from homeassistant.util import dt as dt_util
from homeassistant.components.sensor import SensorEntity
from homeassistant.const import STATE_UNAVAILABLE

from .const import (
    DOMAIN,
    CONF_FROM,
    CONF_TO,
    CONF_TIME_START,
    CONF_TIME_END,
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
)
from .coordinator import SncfUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

def parse_datetime(dt_str):
    if dt_str is None:
        return None
    try:
        naive = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
        return dt_util.as_local(naive)  # Rend le datetime "aware" dans le fuseau local
    except Exception:
        return None

def format_time(dt_str):
    dt = parse_datetime(dt_str)
    if not dt:
        return "N/A"  # Valeur fallback
    return dt.strftime("%d/%m/%Y - %H:%M")

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: SncfUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]

    departure = entry.data.get(CONF_FROM)
    arrival = entry.data.get(CONF_TO)
    departure_name = entry.data.get("departure_name", departure)
    arrival_name = entry.data.get("arrival_name", arrival)
    time_start = entry.data.get(CONF_TIME_START, "07:00")
    time_end = entry.data.get(CONF_TIME_END, "10:00")
    update_interval = DEFAULT_UPDATE_INTERVAL
    outside_interval = DEFAULT_OUTSIDE_INTERVAL

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
    train_sensors = [SncfTrainSensor(main_sensor, index) for index in range(3)]

    # Lier les capteurs enfants pour mise à jour automatique
    for s in train_sensors:
        main_sensor._child_sensors.append(s)

    async_add_entities([main_sensor] + train_sensors, True)


class SncfJourneySensor(SensorEntity):
    def __init__(
        self,
        coordinator,
        departure,
        arrival,
        departure_name,
        arrival_name,
        start_time,
        end_time,
        update_interval,
        outside_interval,
    ):
        self.coordinator = coordinator
        self.departure = departure
        self.arrival = arrival
        self.dep_name = departure_name
        self.arr_name = arrival_name
        self.start_time = start_time
        self.end_time = end_time
        self.update_interval = update_interval
        self.outside_interval = outside_interval

        self._attr_name = f"SNCF: {self.dep_name} → {self.arr_name}"
        self._attr_icon = "mdi:train"
        self._attr_native_unit_of_measurement = "trajets"
        self._attr_unique_id = f"sncf_trains_{self.departure}_{self.arrival}"

        self._journeys = []
        self._state = None
        self._attr_extra_state_attributes = {}

        self._next_update_time = datetime.min

        # Liste des capteurs enfants à mettre à jour quand on update
        self._child_sensors = []

    @property
    def state(self):
        return self._state

    def get_interval(self) -> timedelta:
        now = dt_util.now()
        h_start, m_start = map(int, self.start_time.split(":"))
        dt_start = now.replace(hour=h_start, minute=m_start, second=0, microsecond=0)
        h_end, m_end = map(int, self.end_time.split(":"))
        dt_end = now.replace(hour=h_end, minute=m_end, second=0, microsecond=0)

        if now < dt_start - timedelta(hours=2):
            return timedelta(minutes=self.outside_interval)
        return timedelta(minutes=self.update_interval)

    async def async_update(self):
        now = datetime.now()
        if now >= self._next_update_time:
            await self.coordinator.async_request_refresh()
            self._next_update_time = now + self.get_interval()

        if not self.coordinator.last_update_success:
            self._state = STATE_UNAVAILABLE
            self._clear_data()
            if self.entity_id is not None:
                self.async_write_ha_state()
            return

        journeys = self.coordinator.data or []
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
            base_arrival = parse_datetime(section.get("base_arrival_date_time"))

            if arr_time and base_arrival:
                delay = int((arr_time - base_arrival).total_seconds() / 60)
            else:
                delay = 0
            delays.append(delay)
            if i == 0:
                next_delay = delay

            next_trains.append(format_time(j.get("departure_date_time")))
            trains_summary.append(
                {
                    "departure_time": format_time(j.get("departure_date_time")),
                    "arrival_time": format_time(j.get("arrival_date_time")),
                    "base_departure_time": base_dep,
                    "base_arrival_time": base_arr,
                    "departure_stop_id": self.coordinator.departure,
                    "arrival_stop_id": self.coordinator.arrival,
                    "direction": section.get("display_informations", {}).get("direction", ""),
                    "physical_mode": section.get("display_informations", {}).get("physical_mode", ""),
                    "commercial_mode": section.get("display_informations", {}).get("commercial_mode", ""),
                    "delay_minutes": delay,
                    "has_delay": delay > 0,
                }
            )

        self._attr_extra_state_attributes = {
            "next_trains": next_trains,
            "delay_minutes": delays,
            "has_delay": next_delay > 0 if next_delay is not None else False,
            "next_delay_minutes": next_delay,
            "trains_summary": trains_summary,
        }
        self._state = len(journeys)

        # Mettre à jour les capteurs enfants
        for child in self._child_sensors:
            child.async_update_from_main()

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
        self._state = "N/A"
        self._attr_extra_state_attributes = {}
        if self.entity_id is not None:
            self.async_write_ha_state()

    @property
    def extra_state_attributes(self):
        return self._attr_extra_state_attributes
