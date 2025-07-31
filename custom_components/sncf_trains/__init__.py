import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SncfApiClient
from .const import DOMAIN, CONF_API_KEY, CONF_FROM

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SNCF integration from a config entry."""
    api_key = entry.data[CONF_API_KEY]
    departure = entry.data[CONF_FROM]

    session = async_get_clientsession(hass)
    api_client = SncfApiClient(session, api_key)

    try:
        # Test de connexion pour valider les données
        departures = await api_client.fetch_departures(stop_id=departure, max_results=1)
        if departures is None:
            raise ConfigEntryNotReady("Impossible de récupérer les départs")
    except Exception as err:
        _LOGGER.error("Erreur de connexion à l'API SNCF: %s", err)
        raise ConfigEntryNotReady from err

    # Stockage dans hass.data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "entry": entry,
        "api_client": api_client,
    }

    # Charger la plateforme sensor
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unloading a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
