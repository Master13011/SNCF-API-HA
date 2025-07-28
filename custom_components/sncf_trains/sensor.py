from datetime import datetime
from homeassistant.helpers.entity import Entity
from .const import DOMAIN, CONF_API_KEY, CONF_STATION, CONF_FROM_HOUR, CONF_TO_HOUR
from .api import fetch_departures

async def async_setup_entry(hass, config_entry, async_add_entities):
    api_key = config_entry.data[CONF_API_KEY]
    station_code = config_entry.data[CONF_STATION]
    from_hour = config_entry.data[CONF_FROM_HOUR]
    to_hour = config_entry.data[CONF_TO_HOUR]

    async_add_entities([
        SNCFTrainSensor(api_key, station_code, from_hour, to_hour)
    ])

class SNCFTrainSensor(Entity):
    def __init__(self, api_key, station_code, from_hour, to_hour):
        self._api_key = api_key
        self._station_code = station_code
        self._from_hour = from_hour
        self._to_hour = to_hour
        self._state = None
        self._attributes = {
            "last_update": None,
            "trains": []
        }

    @property
    def name(self):
        return "SNCF Trains"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        now = datetime.now()
        start_dt = now.replace(hour=int(self._from_hour[:2]), minute=int(self._from_hour[3:]), second=0)
        end_dt = now.replace(hour=int(self._to_hour[:2]), minute=int(self._to_hour[3:]), second=0)

        results = await fetch_departures(self._api_key, self._station_code, start_dt, end_dt)
        self._state = len(results)
        self._attributes["last_update"] = now.strftime("%Y-%m-%d %H:%M:%S")
        self._attributes["trains"] = results