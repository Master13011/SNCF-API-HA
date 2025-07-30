from homeassistant import config_entries
import voluptuous as vol
import aiohttp
import base64

from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_FROM,
    CONF_TO,
    CONF_TIME_START,
    CONF_TIME_END,
)

API_BASE = "https://api.sncf.com/v1/coverage/sncf"

def encode_token(api_key: str) -> str:
    """Encode the API key for Basic Auth."""
    token_str = f"{api_key}:"
    return base64.b64encode(token_str.encode()).decode()

class SncfTrainsConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.api_key = None
        self.departure_city = None
        self.departure_station = None
        self.arrival_city = None
        self.arrival_station = None
        self.time_start = "07:00"
        self.time_end = "10:00"
        self.departure_options = {}
        self.arrival_options = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.api_key = user_input[CONF_API_KEY]
            if not await self._validate_api_key(self.api_key):
                errors["base"] = "invalid_api_key"
            else:
                return await self.async_step_departure_city()
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_API_KEY): str}),
            errors=errors,
        )

    async def async_step_departure_city(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.departure_city = user_input["departure_city"]
            stations = await self._fetch_stations(self.departure_city)
            if not stations:
                errors["base"] = "no_stations"
            else:
                self.departure_options = {s["id"]: s for s in stations}
                return await self.async_step_departure_station()
        return self.async_show_form(
            step_id="departure_city",
            data_schema=vol.Schema({vol.Required("departure_city"): str}),
            errors=errors,
        )

    async def async_step_departure_station(self, user_input=None):
        if user_input is not None:
            self.departure_station = user_input["departure_station"]
            return await self.async_step_arrival_city()
        options = {
            k: f'{v["name"]} ({k.split(":")[-1]})'
            for k, v in self.departure_options.items()
        }
        return self.async_show_form(
            step_id="departure_station",
            data_schema=vol.Schema({vol.Required("departure_station"): vol.In(options)}),
        )

    async def async_step_arrival_city(self, user_input=None):
        errors = {}
        if user_input is not None:
            self.arrival_city = user_input["arrival_city"]
            stations = await self._fetch_stations(self.arrival_city)
            if not stations:
                errors["base"] = "no_stations"
            else:
                self.arrival_options = {s["id"]: s for s in stations}
                return await self.async_step_arrival_station()
        return self.async_show_form(
            step_id="arrival_city",
            data_schema=vol.Schema({vol.Required("arrival_city"): str}),
            errors=errors,
        )

    async def async_step_arrival_station(self, user_input=None):
        if user_input is not None:
            self.arrival_station = user_input["arrival_station"]
            return await self.async_step_time_range()
        options = {
            k: f'{v["name"]} ({k.split(":")[-1]})'
            for k, v in self.arrival_options.items()
        }
        return self.async_show_form(
            step_id="arrival_station",
            data_schema=vol.Schema({vol.Required("arrival_station"): vol.In(options)}),
        )

    async def async_step_time_range(self, user_input=None):
        if user_input is not None:
            self.time_start = user_input[CONF_TIME_START]
            self.time_end = user_input[CONF_TIME_END]
            dep_name = self.departure_options.get(self.departure_station, {}).get("name", self.departure_station)
            arr_name = self.arrival_options.get(self.arrival_station, {}).get("name", self.arrival_station)
            return self.async_create_entry(
                title=f"SNCF: {dep_name} → {arr_name}",
                data={
                    CONF_API_KEY: self.api_key,
                    CONF_FROM: self.departure_station,
                    CONF_TO: self.arrival_station,
                    "departure_name": dep_name,
                    "arrival_name": arr_name,
                    CONF_TIME_START: self.time_start,
                    CONF_TIME_END: self.time_end,
                },
            )
        return self.async_show_form(
            step_id="time_range",
            data_schema=vol.Schema({
                vol.Required(CONF_TIME_START, default=self.time_start): str,
                vol.Required(CONF_TIME_END, default=self.time_end): str,
            }),
        )

    async def _fetch_stations(self, query):
        token = encode_token(self.api_key)
        url = f"{API_BASE}/places"
        params = {"q": query, "type[]": "stop_point"}
        headers = {"Authorization": f"Basic {token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, params=params) as resp:
                    if resp.status != 200:
                        return []
                    data = await resp.json()
                    return data.get("places", [])
        except Exception:
            return []

    async def _validate_api_key(self, api_key):
        token = encode_token(api_key)
        url = f"{API_BASE}/places?q=paris&type[]=stop_point"
        headers = {"Authorization": f"Basic {token}"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    return resp.status == 200
        except Exception:
            return False


    @staticmethod
    def async_get_options_flow(config_entry):
        from .options_flow import SncfOptionsFlowHandler
        return SncfOptionsFlowHandler(config_entry)

