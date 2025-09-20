"""The SNCF Train integration."""

import logging

from homeassistant.config_entries import ConfigEntry, ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_registry import Platform

from .const import (
    CONF_API_KEY,
    CONF_ARRIVAL_NAME,
    CONF_DEPARTURE_NAME,
    CONF_FROM,
    CONF_TIME_END,
    CONF_TIME_START,
    CONF_TO,
    CONF_TRAIN_COUNT,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
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
                CONF_UPDATE_INTERVAL: entry.data.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                )
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
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> None:
    """Reload entry if change option."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_migrate_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> bool:
    """Migrate old config entries to move API key to options."""
    data = dict(entry.data)
    options = dict(entry.options)
    updated = False

    if CONF_API_KEY in options:
        data.setdefault(CONF_API_KEY, options.pop(CONF_API_KEY))
        updated = True

    if updated:
        hass.config_entries.async_update_entry(entry, data=data, options=options)

        time_start = options[CONF_TIME_START]
        time_end = options[CONF_TIME_END]
        unique_id = f"{data[CONF_FROM]}_{data[CONF_TO]}_{time_start}_{time_end}"
        title = f"Trajet: {data[CONF_DEPARTURE_NAME]} → {data[CONF_ARRIVAL_NAME]} ({time_start} - {time_end})"
        subentry_data = {
            CONF_FROM: data[CONF_FROM],
            CONF_TO: data[CONF_TO],
            CONF_DEPARTURE_NAME: data[CONF_DEPARTURE_NAME],
            CONF_ARRIVAL_NAME: data[CONF_ARRIVAL_NAME],
            CONF_TIME_START: options[CONF_TIME_START],
            CONF_TIME_END: options[CONF_TIME_END],
            CONF_TRAIN_COUNT: options[CONF_TRAIN_COUNT],
        }

        subentry = ConfigSubentry(
            title=title,
            data=subentry_data,
            subentry_id=entry.entry_id,
            subentry_type="train",
            unique_id=unique_id,
        )
        hass.config_entries.async_add_subentry(entry, subentry)

    return True
