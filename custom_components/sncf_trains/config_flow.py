import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_API_KEY, CONF_STATION, CONF_FROM_HOUR, CONF_TO_HOUR
from .gare_lookup import find_station_code

class SNCFConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            station_code = await find_station_code(user_input[CONF_STATION], user_input[CONF_API_KEY])
            if not station_code:
                errors["station"] = "invalid_station"
            else:
                return self.async_create_entry(
                    title=f"SNCF: {user_input[CONF_STATION]}",
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_STATION: station_code,
                        CONF_FROM_HOUR: user_input[CONF_FROM_HOUR],
                        CONF_TO_HOUR: user_input[CONF_TO_HOUR],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_API_KEY): str,
                vol.Required(CONF_STATION): str,
                vol.Required(CONF_FROM_HOUR, default="07:00"): str,
                vol.Required(CONF_TO_HOUR, default="10:00"): str,
            }),
            errors=errors,
        )