"""The SNCF Train integration."""

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
)
from .coordinator import SncfUpdateCoordinator

type SncfDataConfigEntry = ConfigEntry[SncfUpdateCoordinator]

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.CALENDAR]


async def async_setup_entry(hass: HomeAssistant, entry: SncfDataConfigEntry) -> bool:
    """Set up SNCF Train as config entry."""
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
        time_start = options.pop(CONF_TIME_START)
        time_end = options.pop(CONF_TIME_END)
        train_count = options.pop(CONF_TRAIN_COUNT)
        from_ = data.pop(CONF_FROM)
        to_ = data.pop(CONF_TO)
        dep_name = data.pop(CONF_DEPARTURE_NAME)
        arr_name = data.pop(CONF_ARRIVAL_NAME)
        subentry_id = entry.entry_id
        subentry_data = {
            CONF_FROM: from_,
            CONF_TO: to_,
            CONF_DEPARTURE_NAME: dep_name,
            CONF_ARRIVAL_NAME: arr_name,
            CONF_TIME_START: time_start,
            CONF_TIME_END: time_end,
            CONF_TRAIN_COUNT: train_count,
        }

        hass.config_entries.async_update_entry(
            entry, data=data, options=options, unique_id="sncf_trains"
        )
        subentry = ConfigSubentry(
            title=f"Trajet: {dep_name} → {arr_name} ({time_start} - {time_end})",
            data=subentry_data,
            subentry_id=subentry_id,
            subentry_type="train",
            unique_id=f"{from_}_{to_}_{time_start}_{time_end}",
        )
        hass.config_entries.async_add_subentry(entry, subentry)

    return True
