import logging
import asyncio
from datetime import datetime, time, timedelta
import re

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN, CONF_API_KEY, CONF_FROM, CONF_TO, CONF_TIME_START, CONF_TIME_END

_LOGGER = logging.getLogger(__name__)

API_URL = "https://api.sncf.com/v1/coverage/sncf/journeys"

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    api_key = entry.data[CONF_API_KEY]
    departure = entry.data[CONF_FROM]
    arrival = entry.data[CONF_TO]
    departure_name = entry.data.get("departure_name", departure)
    arrival_name = entry.data.get("arrival_name", arrival)
    time_start = entry.data.get(CONF_TIME_START, "07:00")
    time_end = entry.data.get(CONF_TIME_END, "10:00")

    sensor = SncfJourneySensor(hass, api_key, departure, arrival, departure_name, arrival_name, time_start, time_end)

    async def async_update_data(_=None):
        await sensor.async_update()

    async_track_time_interval(hass, async_update_data, timedelta(minutes=10))
    await async_update_data()

    async_add_entities([sensor], True)
    return True


class SncfJourneySensor(SensorEntity):
    def __init__(self, hass, api_key, departure, arrival, departure_name, arrival_name, time_start, time_end):
        self.hass = hass
        self._api_key = api_key
        self._departure = departure
        self._arrival = arrival
        self._departure_name = departure_name
        self._arrival_name = arrival_name
        self._time_start = time_start
        self._time_end = time_end

        self._attr_name = f"SNCF: {self._departure_name} → {self._arrival_name}"
        self._attr_icon = "mdi:train"
        self._attr_native_unit_of_measurement = "trajets"
        self._attr_device_class = None
        self._attr_native_value = 0
        self._attr_unique_id = self._generate_unique_id()

        self._attr_extra_state_attributes = {
            "journeys": [],
            "next_trains": [],
            "departure_station": self._departure,
            "arrival_station": self._arrival,
            "departure_name": self._departure_name,
            "arrival_name": self._arrival_name,
        }

        self._session = async_get_clientsession(hass)

    def _generate_unique_id(self):
        clean_dep = re.sub(r"[^a-z0-9_]", "_", self._departure.lower())
        clean_arr = re.sub(r"[^a-z0-9_]", "_", self._arrival.lower())
        return f"sncf_journeys_{clean_dep}_{clean_arr}"

    async def async_update(self):
        params = {
            "from": self._departure,
            "to": self._arrival,
            "datetime": self._get_datetime_start(),
            "count": 10,
        }
        headers = {
            "Authorization": self._api_key
        }

        try:
            async with self._session.get(API_URL, params=params, headers=headers, timeout=10) as resp:
                if resp.status != 200:
                    _LOGGER.error(f"Erreur API SNCF : HTTP {resp.status}")
                    self._clear_data()
                    return

                data = await resp.json()
                journeys = data.get("journeys", [])
                filtered = self._filter_journeys_by_time(journeys)

                readable_trains = []
                for j in filtered:
                    dep = datetime.strptime(j["departure"], "%Y%m%dT%H%M%S")
                    arr = datetime.strptime(j["arrival"], "%Y%m%dT%H%M%S")
                    duration = j.get("duration_min", "?")
                    transfers = j.get("nb_transfers", 0)
                    status = j.get("status", "")
                    delay_note = "retards" if status == "SIGNIFICANT_DELAYS" else "direct" if transfers == 0 else f"{transfers} correspondance(s)"
                    readable = f"{dep.strftime('%H:%M')} ➜ {arr.strftime('%H:%M')} ({duration} min, {delay_note})"
                    readable_trains.append(readable)

                    j["departure"] = dep.strftime("%d/%m/%Y %H:%M")
                    j["arrival"] = arr.strftime("%d/%m/%Y %H:%M")

                self._attr_extra_state_attributes["journeys"] = filtered
                self._attr_extra_state_attributes["next_trains"] = readable_trains
                self._attr_native_value = len(filtered)

        except asyncio.TimeoutError:
            _LOGGER.error("Timeout lors de la requête API SNCF")
            self._clear_data()
        except Exception as e:
            _LOGGER.error(f"Erreur lors de la récupération des trajets SNCF: {e}")
            self._clear_data()


    def _clear_data(self):
        self._attr_extra_state_attributes["journeys"] = []
        self._attr_extra_state_attributes["next_trains"] = []
        self._attr_native_value = 0

    def _get_datetime_start(self):
        now = datetime.now()
        hour, minute = map(int, self._time_start.split(":"))
        dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Si on est passé après l'heure de fin, on prend demain à l'heure de début
        end_hour, end_minute = map(int, self._time_end.split(":"))
        end_dt = now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if now > end_dt:
            dt += timedelta(days=1)
        return dt.strftime("%Y%m%dT%H%M%S")

    def _filter_journeys_by_time(self, journeys):
        start_h, start_m = map(int, self._time_start.split(":"))
        end_h, end_m = map(int, self._time_end.split(":"))
        start_time = time(start_h, start_m)
        end_time = time(end_h, end_m)

        filtered = []
        for j in journeys:
            departure_dt_str = j.get("departure_date_time")
            if not departure_dt_str or len(departure_dt_str) < 15:
                continue
            try:
                dep_dt = datetime.strptime(departure_dt_str, "%Y%m%dT%H%M%S")
                dep_time = dep_dt.time()
            except Exception:
                continue

            # Permet de gérer la plage qui traverse minuit
            if start_time <= end_time:
                if start_time <= dep_time <= end_time:
                    filtered.append({
                        "departure": departure_dt_str,
                        "arrival": j.get("arrival_date_time"),
                        "duration_min": j.get("duration") // 60 if j.get("duration") else None,
                        "nb_transfers": j.get("nb_transfers"),
                        "status": j.get("status"),
                    })
            else:
                # plage qui traverse minuit (ex: 22:00 à 02:00)
                if dep_time >= start_time or dep_time <= end_time:
                    filtered.append({
                        "departure": departure_dt_str,
                        "arrival": j.get("arrival_date_time"),
                        "duration_min": j.get("duration") // 60 if j.get("duration") else None,
                        "nb_transfers": j.get("nb_transfers"),
                        "status": j.get("status"),
                    })

        return filtered

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, f"sncf_{self._departure}_{self._arrival}")},
            "name": "SNCF Sensor",
            "manufacturer": "Master13011",
            "model": "API"
        }
