"""The SNCF Train integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import Platform

from .const import (
    CONF_API_KEY,
    CONF_TIME_END,
    CONF_TIME_START,
    DEFAULT_TIME_END,
    DEFAULT_TIME_START,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .coordinator import SncfUpdateCoordinator

type SncfDataConfigEntry = ConfigEntry[SncfUpdateCoordinator]

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> bool:
    """Set up SNCF Train as config entry."""
    if not entry.options:
        hass.config_entries.async_update_entry(
            entry,
            options={
                CONF_TIME_START: entry.data.get(CONF_TIME_START, DEFAULT_TIME_START),
                CONF_TIME_END: entry.data.get(CONF_TIME_END, DEFAULT_TIME_END),
                "update_interval": entry.data.get(
                    "update_interval", DEFAULT_UPDATE_INTERVAL
                ),
            },
        )

    api_key = entry.options.get(CONF_API_KEY) or entry.data.get(CONF_API_KEY)
    if not api_key:
        _LOGGER.error("API key not found in options")
        return False

    coordinator = SncfUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> None:
    """Reload entry if change option."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> bool:
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
