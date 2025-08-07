import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import SncfApiClient
from .const import DOMAIN, CONF_API_KEY, CONF_FROM, CONF_TO, CONF_TIME_START, CONF_TIME_END, DEFAULT_UPDATE_INTERVAL, DEFAULT_TIME_START, DEFAULT_TIME_END
from .coordinator import SncfUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not entry.options:
        hass.config_entries.async_update_entry(entry, options={
            CONF_TIME_START: entry.data.get(CONF_TIME_START, DEFAULT_TIME_START),
            CONF_TIME_END: entry.data.get(CONF_TIME_END, DEFAULT_TIME_END),
            "update_interval": entry.data.get("update_interval", DEFAULT_UPDATE_INTERVAL),
        })

    api_key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY)
    departure = entry.data[CONF_FROM]
    arrival = entry.data[CONF_TO]

    if not api_key:
        _LOGGER.error("API key not found in options")
        return False

    time_start = entry.options.get(CONF_TIME_START, DEFAULT_TIME_START)
    time_end = entry.options.get(CONF_TIME_END, DEFAULT_TIME_END)
    update_interval = entry.options.get("update_interval", DEFAULT_UPDATE_INTERVAL)

    session = async_get_clientsession(hass)
    api_client = SncfApiClient(session, api_key)

    try:
        departures = await api_client.fetch_departures(stop_id=departure, max_results=1)
        if departures is None:
            raise ConfigEntryNotReady("Failed to fetch departures from SNCF API")
    except Exception as err:
        _LOGGER.error("Error connecting to SNCF API: %s", err)
        raise ConfigEntryNotReady from err

    coordinator = SncfUpdateCoordinator(
        hass,
        api_client,
        departure,
        arrival,
        time_start,
        time_end,
        update_interval=update_interval
    )
    await coordinator.async_refresh()
    if not coordinator.last_update_success:
        raise ConfigEntryNotReady("Initial data fetch failed")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, ["sensor"])
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to move API key to options."""
    data = dict(entry.data)
    options = dict(entry.options)
    updated = False

    if CONF_API_KEY in data:
        options.setdefault(CONF_API_KEY, data.pop(CONF_API_KEY))
        updated = True

    if updated:
        hass.config_entries.async_update_entry(entry, data=data, options=options)
        _LOGGER.info("Migrated SNCF config entry to move api_key to options.")

    return True