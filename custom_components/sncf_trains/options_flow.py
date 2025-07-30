from homeassistant import config_entries
import voluptuous as vol

from .const import DOMAIN

class SncfOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            # Met à jour les options
            self.hass.config_entries.async_update_entry(self.config_entry, options=user_input)
            # Recharge l'intégration pour appliquer les nouvelles options
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required("update_interval", default=self.config_entry.options.get("update_interval", 2)): int,
                vol.Required("outside_interval", default=self.config_entry.options.get("outside_interval", 60)): int,
            })
        )
