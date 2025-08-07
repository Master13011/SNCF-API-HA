from homeassistant.config_entries import OptionsFlow
import voluptuous as vol

from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_TRAIN_COUNT,
    DEFAULT_TIME_START,
    DEFAULT_TIME_END,
    CONF_API_KEY,
    CONF_TIME_START,
    CONF_TIME_END,
)

class SncfTrainsOptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry):
        super().__init__()

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    CONF_API_KEY: user_input[CONF_API_KEY],
                    "update_interval": user_input["update_interval"],
                    "outside_interval": user_input["outside_interval"],
                    "train_count": user_input["train_count"],
                    CONF_TIME_START: user_input["time_start"],
                    CONF_TIME_END: user_input["time_end"],
                },
            )

        options = self.config_entry.options if self.config_entry else {}
        data_fallback = self.config_entry.data if self.config_entry else {}

        values = {
            CONF_API_KEY: options.get(CONF_API_KEY, ""),
            "update_interval": options.get("update_interval", DEFAULT_UPDATE_INTERVAL),
            "outside_interval": options.get("outside_interval", DEFAULT_OUTSIDE_INTERVAL),
            "train_count": options.get("train_count", DEFAULT_TRAIN_COUNT),
            CONF_TIME_START: options.get(CONF_TIME_START, data_fallback.get(CONF_TIME_START, DEFAULT_TIME_START)),
            CONF_TIME_END: options.get(CONF_TIME_END, data_fallback.get(CONF_TIME_END, DEFAULT_TIME_END)),
        }

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY, default=values[CONF_API_KEY]): str,
                vol.Required("update_interval", default=values["update_interval"]): int,
                vol.Required("outside_interval", default=values["outside_interval"]): int,
                vol.Required("train_count", default=values["train_count"]): int,
                vol.Required("time_start", default=values[CONF_TIME_START]): str,
                vol.Required("time_end", default=values[CONF_TIME_END]): str,
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
