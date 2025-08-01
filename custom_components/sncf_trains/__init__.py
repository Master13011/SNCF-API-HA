import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SncfApiClient
from .const import (
    DOMAIN,
    CONF_API_KEY,
    CONF_FROM,
    CONF_TO,
    CONF_TIME_START,
    CONF_TIME_END,
    DEFAULT_UPDATE_INTERVAL,
)
from .coordinator import SncfUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api_key = entry.data[CONF_API_KEY]
    departure = entry.data[CONF_FROM]
    arrival = entry.data[CONF_TO]
    time_start = entry.data.get(CONF_TIME_START, "07:00")
    time_end = entry.data.get(CONF_TIME_END, "10:00")

    session = async_get_clientsession(hass)
    api_client = SncfApiClient(session, api_key)

    # Valider la connexion API
    try:
        departures = await api_client.fetch_departures(stop_id=departure, max_results=1)
        if departures is None:
            raise ConfigEntryNotReady("Failed to fetch departures from SNCF API")
    except Exception as err:
        _LOGGER.error("Error connecting to SNCF API: %s", err)
        raise ConfigEntryNotReady from err

    # Créer le coordinator, on envoie l'intervalle de mise à jour
    coordinator = SncfUpdateCoordinator(
        hass,
        api_client,
        departure,
        arrival,
        time_start,
        time_end,
        update_interval=DEFAULT_UPDATE_INTERVAL
    )
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial data fetch failed")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
