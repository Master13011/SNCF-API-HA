import logging
from datetime import datetime
from homeassistant.helpers.entity import Entity
from .api import fetch_departures, search_stations
from .const import DOMAIN, CONF_TOKEN, CONF_GARE, CONF_START, CONF_END

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([SNCFTrainSensor(entry)])

class SNCFTrainSensor(Entity):

    def __init__(self, entry):
        self._entry = entry
        self._api_token = entry.data[CONF_TOKEN]
        self._station_id = entry.data[CONF_GARE]
        self._time_start = entry.data.get(CONF_START, "06:00")
        self._time_end = entry.data.get(CONF_END, "22:00")
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        return f"SNCF Trains ({self._station_id})"

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        _LOGGER.debug("Mise à jour du capteur SNCF Trains")
        # Récupère les départs bruts
        try:
            departures = await self.hass.async_add_executor_job(
                fetch_departures, self._api_token, self._station_id)
        except Exception as e:
            _LOGGER.error(f"Erreur fetch_departures SNCF : {e}")
            self._state = "Erreur API"
            self._attributes = {}
            return

        try:
            st = datetime.strptime(self._time_start, "%H:%M").time()
            et = datetime.strptime(self._time_end, "%H:%M").time()
        except Exception as e:
            _LOGGER.error(f"Erreur parse heure filtre : {e}")
            st = datetime.strptime("06:00", "%H:%M").time()
            et = datetime.strptime("22:00", "%H:%M").time()

        trains = []
        for train in departures:
            try:
                dt_str = train["stop_date_time"]["departure_date_time"]
                dt = datetime.strptime(dt_str, "%Y%m%dT%H%M%S")
                if st <= dt.time() <= et:
                    base_dt_str = train["stop_date_time"]["base_departure_date_time"]
                    base_dt = datetime.strptime(base_dt_str, "%Y%m%dT%H%M%S")

                    delay = int((dt - base_dt).total_seconds() // 60)

                    infos = train.get("display_informations", {}).get("additional_informations", [])
                    canceled = any("canceled" in info.lower() for info in infos)

                    trains.append({
                        "time": dt.strftime("%H:%M"),
                        "destination": train["display_informations"].get("direction"),
                        "retard": delay,
                        "annule": canceled,
                    })
            except Exception as e:
                _LOGGER.debug(f"Erreur parsing train: {e}")

        self._state = len(trains)
        self._attributes = {
            "station": self._station_id,
            "trains": trains,
            "time_start": self._time_start,
            "time_end": self._time_end
        }
