import logging
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_TOKEN, CONF_GARE, CONF_START, CONF_END
from .api import search_stations

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_TOKEN): str,
})

STEP_STATION_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_GARE): str,
})

STEP_TIME_DATA_SCHEMA = vol.Schema({
    vol.Required(CONF_START, default="06:00"): str,
    vol.Required(CONF_END, default="22:00"): str,
})

class SNCFConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.api_token = None
        self.station = None
        self.station_id = None
        self.time_start = "06:00"
        self.time_end = "22:00"

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input:
            # On vérifie simplement la présence du token ici
            self.api_token = user_input[CONF_TOKEN]
            # Passe à la sélection de la station
            return await self.async_step_station()
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_station(self, user_input=None):
        errors = {}
        stations_list = []
        if user_input:
            query_text = user_input[CONF_GARE].strip()
            if not query_text:
                errors["base"] = "empty_query"
            else:
                try:
                    stations_raw = await self.hass.async_add_executor_job(
                        search_stations, self.api_token, query_text)
                except Exception as e:
                    _LOGGER.error(f"Erreur API SNCF recherche gare : {e}")
                    errors["base"] = "api_error"
                else:
                    if not stations_raw:
                        errors["base"] = "not_found"
                    else:
                        # On propose la sélection de la première gare trouvée (pour simplifier ce flow)
                        station = stations_raw[0]
                        self.station_id = station["id"]
                        self.station = station["name"]
                        return await self.async_step_time()
        return self.async_show_form(
            step_id="station",
            data_schema=STEP_STATION_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"example": "riquier, nice, paris, lyon"}
        )

    async def async_step_time(self, user_input=None):
        errors = {}
        if user_input:
            start = user_input[CONF_START]
            end = user_input[CONF_END]
            # Simple valid check : format HH:MM
            from datetime import datetime
            try:
                datetime.strptime(start, "%H:%M")
                datetime.strptime(end, "%H:%M")
            except ValueError:
                errors["base"] = "invalid_time"
            else:
                self.time_start = start
                self.time_end = end
                # Crée l'entrée d'intégration
                return self.async_create_entry(
                    title="SNCF Trains – {}".format(self.station),
                    data={
                        CONF_TOKEN: self.api_token,
                        CONF_GARE: self.station_id,
                        CONF_START: self.time_start,
                        CONF_END: self.time_end,
                    }
                )
        return self.async_show_form(
            step_id="time",
            data_schema=STEP_TIME_DATA_SCHEMA,
            errors=errors
        )
