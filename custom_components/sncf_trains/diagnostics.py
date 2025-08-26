"""Diagnostics support for SNCF integration."""
from __future__ import annotations
from typing import Any
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dumps import async_redact_data
from .const import DOMAIN, CONF_API_KEY

TO_REDACT = {CONF_API_KEY}

async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data: dict[str, Any] = {}

    data["config_entry"] = {
        "title": entry.title,
        "data": async_redact_data(entry.data, TO_REDACT),
        "options": async_redact_data(entry.options, TO_REDACT),
        "entry_id": entry.entry_id,
        "version": entry.version,
    }

    coordinator = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if coordinator:
        data["coordinator"] = {
            "departure": coordinator.departure,
            "arrival": coordinator.arrival,
            "time_start": coordinator.time_start,
            "time_end": coordinator.time_end,
            "update_interval": str(coordinator.update_interval),
            "last_update_success": coordinator.last_update_success,
            "last_update_time": str(getattr(coordinator, "last_update_success_time", None)),
            "data_sample": coordinator.data[:3] if coordinator.data else None,
        }
    return data
