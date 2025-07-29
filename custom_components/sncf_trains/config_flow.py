from homeassistant import config_entries
import voluptuous as vol
import aiohttp

from .const import DOMAIN, CONF_API_KEY, CONF_FROM, CONF_TO, CONF_TIME_START, CONF_TIME_END


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

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            self.api_key = user_input[CONF_API_KEY]
            return await self.async_step_departure_city()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str
            }),
            errors=errors
        )

    async def async_step_departure_city(self, user_input=None):
        if user_input is not None:
            self.departure_city = user_input["departure_city"]
            stations = await self._fetch_stations(self.departure_city)
            if not stations:
                return self.async_show_form(
                    step_id="departure_city",
                    data_schema=vol.Schema({
                        vol.Required("departure_city"): str
                    }),
                    errors={"base": "no_stations_found"}
                )
            self.departure_options = {station["id"]: station for station in stations}
            return await self.async_step_departure_station()

        return self.async_show_form(
            step_id="departure_city",
            data_schema=vol.Schema({
                vol.Required("departure_city"): str
            })
        )

    async def async_step_departure_station(self, user_input=None):
        if user_input is not None:
            self.departure_station = user_input["departure_station"]
            return await self.async_step_arrival_city()

        options = {
            station_id: f"{station_data['name']} ({station_id.split(':')[-1]})"
            for station_id, station_data in self.departure_options.items()
        }

        return self.async_show_form(
            step_id="departure_station",
            data_schema=vol.Schema({
                vol.Required("departure_station"): vol.In(options)
            })
        )

    async def async_step_arrival_city(self, user_input=None):
        if user_input is not None:
            self.arrival_city = user_input["arrival_city"]
            stations = await self._fetch_stations(self.arrival_city)
            if not stations:
                return self.async_show_form(
                    step_id="arrival_city",
                    data_schema=vol.Schema({
                        vol.Required("arrival_city"): str
                    }),
                    errors={"base": "no_stations_found"}
                )
            self.arrival_options = {station["id"]: station for station in stations}
            return await self.async_step_arrival_station()

        return self.async_show_form(
            step_id="arrival_city",
            data_schema=vol.Schema({
                vol.Required("arrival_city"): str
            })
        )

    async def async_step_arrival_station(self, user_input=None):
        if user_input is not None:
            self.arrival_station = user_input["arrival_station"]
            return await self.async_step_time_range()

        options = {
            station_id: f"{station_data['name']} ({station_id.split(':')[-1]})"
            for station_id, station_data in self.arrival_options.items()
        }

        return self.async_show_form(
            step_id="arrival_station",
            data_schema=vol.Schema({
                vol.Required("arrival_station"): vol.In(options)
            })
        )

    async def async_step_time_range(self, user_input=None):
        if user_input is not None:
            self.time_start = user_input[CONF_TIME_START]
            self.time_end = user_input[CONF_TIME_END]

            # Crée un titre lisible avec les deux stations (extraction ID simplifiée)
            dep_name = self.departure_options[self.departure_station]["name"] if self.departure_station in self.departure_options else "Départ"
            arr_name = self.arrival_options[self.arrival_station]["name"] if self.arrival_station in self.arrival_options else "Arrivée"

            title = f"SNCF: {dep_name} → {arr_name}"

            return self.async_create_entry(
                title=title,
                data={
                    CONF_API_KEY: self.api_key,
                    CONF_FROM: self.departure_station,
                    CONF_TO: self.arrival_station,
                    "departure_name": dep_name,
                    "arrival_name": arr_name,
                    CONF_TIME_START: self.time_start,
                    CONF_TIME_END: self.time_end,
                }
            )

        return self.async_show_form(
            step_id="time_range",
            data_schema=vol.Schema({
                vol.Required(CONF_TIME_START, default="07:00"): str,
                vol.Required(CONF_TIME_END, default="10:00"): str
            })
        )

    async def _fetch_stations(self, query):
        url = f"https://api.sncf.com/v1/coverage/sncf/places?q={query}&type[]=stop_area"
        headers = {"Authorization": self.api_key}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return []
                data = await resp.json()
                return [
                    {
                        "id": place["id"],
                        "name": place["name"]
                    }
                    for place in data.get("places", [])
                    if place.get("embedded_type") == "stop_area"
                ]
