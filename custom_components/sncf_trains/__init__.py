"""Init file for sncf_trains integration."""

from homeassistant.helpers import config_entry_flow

async def async_setup(hass, config):
    return True

async def async_setup_entry(hass, entry):
    # Platform setup delegated to sensor.py via async_forward_entry_setups if used
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True

async def async_unload_entry(hass, entry):
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
