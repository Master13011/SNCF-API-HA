import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .api import encode_token, fetch_departures
from .const import CONF_API_KEY, CONF_FROM

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up the SNCF integration from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    departure = entry.data[CONF_FROM]

    # Encode API key for Basic Auth
    token = encode_token(api_key)

    try:
        # Validate API access by fetching one departure
        departures = await fetch_departures(token=token, stop_id=departure, max_results=1)
        if departures is None:
            _LOGGER.warning("SNCF API accessible but no departure data for %s", departure)
    except Exception as err:
        _LOGGER.error("Error connecting to SNCF API: %s", err)
        raise ConfigEntryNotReady from err

    # Forward setup to the sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the SNCF integration."""
    return await hass.config_entries.async_unload_platforms(entry, ["sensor"])
