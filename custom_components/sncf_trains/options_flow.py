from homeassistant import config_entries
import voluptuous as vol
from .const import (
    DEFAULT_UPDATE_INTERVAL,
    DEFAULT_OUTSIDE_INTERVAL,
    DEFAULT_TRAIN_COUNT,
)

class SncfTrainsOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        super().__init__()

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("update_interval", default=self.config_entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL)): int,
                vol.Required("outside_interval", default=self.config_entry.options.get("outside_interval", DEFAULT_OUTSIDE_INTERVAL)): int,
                vol.Required("train_count", default=self.config_entry.options.get("train_count", DEFAULT_TRAIN_COUNT)): int,
            })
        )
