from homeassistant.config_entries import OptionsFlowWithConfigEntry
import voluptuous as vol
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_TRAIN_COUNT,
    DEFAULT_TIME_START,
    DEFAULT_TIME_END,
    CONF_TIME_START,
    CONF_TIME_END,
)

class SncfTrainsOptionsFlowHandler(OptionsFlowWithConfigEntry):
    def __init__(self, config_entry):
        super().__init__(config_entry)
        # Plus besoin de stocker explicitement config_entry, c'est fait par la classe parente

    async def async_step_init(self, user_input=None):
        config_entry = self.config_entry  # fourni par OptionsFlowWithConfigEntry

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    "update_interval": user_input["update_interval"],
                    "outside_interval": user_input["outside_interval"],
                    "train_count": user_input["train_count"],
                    CONF_TIME_START: user_input["time_start"],
                    CONF_TIME_END: user_input["time_end"],
                }
            )

        data = config_entry.options if config_entry.options else {}
        data = {
            "update_interval": data.get("update_interval", DEFAULT_UPDATE_INTERVAL),
            "outside_interval": data.get("outside_interval", DEFAULT_OUTSIDE_INTERVAL),
            "train_count": data.get("train_count", DEFAULT_TRAIN_COUNT),
            CONF_TIME_START: data.get(CONF_TIME_START, config_entry.data.get(CONF_TIME_START, DEFAULT_TIME_START)),
            CONF_TIME_END: data.get(CONF_TIME_END, config_entry.data.get(CONF_TIME_END, DEFAULT_TIME_END)),
        }

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("update_interval", default=data["update_interval"]): int,
                vol.Required("outside_interval", default=data["outside_interval"]): int,
                vol.Required("train_count", default=data["train_count"]): int,
                vol.Required("time_start", default=data[CONF_TIME_START]): str,
                vol.Required("time_end", default=data[CONF_TIME_END]): str,
            })
        )
